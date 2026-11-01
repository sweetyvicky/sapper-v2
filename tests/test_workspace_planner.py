"""Offline planner validation, real local model transport and bounded DNS tests."""
import copy
import http.server
import importlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from pentest.workspace_store import WorkspaceStore, WorkspaceError
from pentest.workspace_intake import parse_assets
from pentest.models import ModelProfiles, ModelError


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = WorkspaceStore(self.root / 'workspace')
        self.models = ModelProfiles(self.root / 'models', allow_http_loopback=True)
        self.profile = self.models.save(dict(name='fixture', provider='custom',
            base_url='http://127.0.0.1:9/v1', model='fixture', api_key='synthetic-key', timeout_seconds=5))
        draft = self.store.save_draft(dict(name='case', goal='entire goal', context='entire context',
            guidance='initial guidance', assets=parse_assets('http://localhost:8080/old')['assets'],
            model_profile_id=self.profile['id']))
        self.run = self.store.create_run(draft['id'], draft['revision'])
        self.run.update(policy=dict(engagement_id='fixture', expires_at=time.time()+3600,
            allowed_origins=['http://localhost:8080'], allowed_networks=['127.0.0.1/32'],
            denied_networks=[], allowed_tools=['http_get','http_head'],
            budget=dict(requests=30, bytes=1048576, seconds=300, parallel=1),
            max_request_seconds=10, max_response_bytes=32768),
            scope=dict(origins=['http://localhost:8080'], pinned={'localhost':['127.0.0.1']},
            excluded_origins=[], denied_networks=[], enrollment='whole-origin'))
        self.action = dict(asset_id=self.run['draft']['assets'][0]['id'], target='http://localhost:8080/new',
            tool='http_get', role='Scout', description='Observe endpoint', risk=1, evidence_gap=.5)
        self.plan = dict(summary='Observe only', gaps=['Manual testing remains'], actions=[self.action])
        self.evidence = dict(id='e'*32, receipt_id='r-new', target='http://localhost:8080/old',
            tool='http_get', status='succeeded', http_status=200, started_at=20, finished_at=21,
            body_sha256='a'*64, excerpt='bounded observation')
        self.observations = [dict(fact_id='f'*32, valid=True, description='actual observation', evidence=[self.evidence])]
        self.finding = dict(fact_id='f'*32, title='candidate', severity='low', description='detail',
            impact='impact', reproduction='steps', remediation='fix', cwe='', operator_note='')

    def api(self):
        try: return importlib.import_module('pentest.workspace_planner')
        except ImportError: self.fail('data-only workspace planner is missing')

    def denied(self, call):
        with self.assertRaises(WorkspaceError) as caught: call()
        self.assertNotIn('synthetic-key', str(caught.exception))
        return caught.exception

    def prepare(self, **kw):
        args = dict(role='Commander', purpose='plan', guidance=[], observations=[]); args.update(kw)
        return self.api().prepare_call(self.store, self.models, self.run, **args)

    def test_plan_original_asset_new_path_canonical_and_exact_fields(self):
        result = self.api().validate_plan(json.dumps(self.plan), self.run)
        self.assertEqual(result, self.plan)
        self.assertEqual(set(result['actions'][0]), set(self.action))
        self.assertEqual(self.api().validate_plan('```json\n'+json.dumps(self.plan)+'\n```', self.run), self.plan)
        for change in [dict(asset_id='foreign'), dict(target='http://foreign.invalid/'), dict(tool='shell'),
                       dict(approval=True), dict(intent_id='self-approved'), dict(role='Commander'),
                       dict(risk=True), dict(risk=11), dict(evidence_gap=-1), dict(description='a\x00')]:
            data = copy.deepcopy(self.plan); data['actions'][0].update(change)
            self.denied(lambda: self.api().validate_plan(json.dumps(data), self.run))
        run = copy.deepcopy(self.run); run['draft']['assets'][0]['target']='http://other.invalid:8080/'
        self.denied(lambda: self.api().validate_plan(json.dumps(self.plan), run))

    def test_plan_checks_all_pins_exclusions_and_policy_tools(self):
        for scope_patch, policy_patch in [({'pinned':{'localhost':['127.0.0.1','192.0.2.1']}}, {}),
                ({'excluded_origins':['http://localhost:8080']}, {}),
                ({'denied_networks':['127.0.0.0/8']}, {}), ({}, {'denied_networks':['127.0.0.0/8']}),
                ({}, {'allowed_tools':['http_head']}), ({'pinned':{}}, {}),
                ({'pinned':{'localhost':['224.0.0.1']}}, {'allowed_networks':['224.0.0.1/32']})]:
            run = copy.deepcopy(self.run); run['scope'].update(scope_patch); run['policy'].update(policy_patch)
            self.denied(lambda: self.api().validate_plan(json.dumps(self.plan), run))

    def test_entire_frozen_mapping_is_checked_even_without_actions(self):
        run = copy.deepcopy(self.run)
        run['scope']['pinned']['unused.invalid'] = ['192.0.2.1']
        self.denied(lambda: self.api().validate_plan(json.dumps(dict(self.plan,actions=[])),run))
        run = copy.deepcopy(self.run); run['scope']['pinned']['localhost'] = ['127.0.0.1','0.0.0.0']
        self.denied(lambda: self.api().validate_plan(json.dumps(dict(self.plan,actions=[])),run))

    def test_strict_json_bounds_unicode_and_text(self):
        bad = ['{"summary":"a","summary":"b","gaps":[],"actions":[]}',
            json.dumps(self.plan)+' extra', json.dumps(self.plan).replace('"risk": 1','"risk": NaN'),
            json.dumps(dict(summary='\ud800', gaps=[], actions=[])), 'x'*(2*1024*1024+1),
            json.dumps(dict(summary='', gaps=[], actions=[])),
            json.dumps(dict(summary='x', gaps=['x']*101, actions=[])),
            json.dumps(dict(summary='x', gaps=[], actions=[self.action]*501))]
        for content in bad: self.denied(lambda: self.api().validate_plan(content,self.run))

    def test_analysis_only_current_fact_and_narratives(self):
        data = dict(summary='candidate only', gaps=[], findings=[self.finding])
        self.assertEqual(self.api().validate_analysis(json.dumps(data), ['f'*32]), data)
        self.denied(lambda: self.api().validate_analysis(json.dumps(data), []))
        for patch in [dict(status='confirmed'), dict(reporter='self'), dict(approval=True), dict(commands=['x']),
                      dict(severity='urgent'), dict(impact=''), dict(title='a\n'), dict(cwe='x'*81)]:
            modified = copy.deepcopy(data); modified['findings'][0].update(patch)
            self.denied(lambda: self.api().validate_analysis(json.dumps(modified), ['f'*32]))
        data['findings'] *= 51
        self.denied(lambda: self.api().validate_analysis(json.dumps(data), ['f'*32]))

    def review_case(self):
        old = dict(self.evidence, id='b'*32, receipt_id='r-old', started_at=10, finished_at=11)
        return dict(id='c'*32, fact_id='f'*32, reporter='model:old', status='candidate',
            evidence=[old], invalid_reasons=[], title='case', description='original case')

    def test_review_suggestions_require_independent_later_exact_current_evidence(self):
        case = self.review_case()
        data = dict(summary='advisory only', gaps=[], review_suggestions=[dict(
            finding_id=case['id'], evidence_id=self.evidence['id'], outcome='confirmed', note='independent observation')])
        validate = self.api().validate_review
        self.assertEqual(validate(json.dumps(data), [case], self.observations), data)
        for status in ('rejected','inconclusive'):
            changed = dict(case,status=status)
            self.assertEqual(validate(json.dumps(data), [changed], self.observations), data)
        for mutation in ('foreign_case','foreign_evidence','stale','same_receipt','early','wrong_target','multi_target','no_original','bad_note','unknown'):
            cases = [copy.deepcopy(case)]; obs = copy.deepcopy(self.observations); result = copy.deepcopy(data)
            if mutation=='foreign_case': result['review_suggestions'][0]['finding_id']='d'*32
            if mutation=='foreign_evidence': result['review_suggestions'][0]['evidence_id']='d'*32
            if mutation=='stale': obs[0]['valid']=False
            if mutation=='same_receipt': obs[0]['evidence'][0]['receipt_id']='r-old'
            if mutation=='early': obs[0]['evidence'][0]['started_at']=9
            if mutation=='wrong_target': obs[0]['evidence'][0]['target']='http://localhost:8080/new'
            if mutation=='multi_target': cases[0]['evidence'].append(dict(case['evidence'][0],target='http://localhost:8080/new'))
            if mutation=='no_original': cases[0]['evidence']=[]
            if mutation=='bad_note': result['review_suggestions'][0]['note']='a\n'
            if mutation=='unknown': result['review_suggestions'][0]['status']='confirmed'
            self.denied(lambda: validate(json.dumps(result),cases,obs))
        for change in [dict(status='stale'),dict(invalid_reasons=['expired'])]:
            self.denied(lambda: validate(json.dumps(data),[dict(case,**change)],self.observations))
        self.denied(lambda: validate(json.dumps(data), [case], [dict(self.observations[0],fact_id='d'*32)]))

    def test_prepare_preserves_context_all_messages_and_reserves_without_transport(self):
        messages = [self.store.add_message(self.run['id'],dict(request_id=uuid.uuid4().hex,kind='guidance',text='operator '+str(i))) for i in range(3)]
        with mock.patch.object(self.models,'complete',side_effect=AssertionError('transport under lock')):
            result = self.prepare(guidance=messages,observations=self.observations,findings=[self.review_case()])
        prompt = json.loads(result['messages'][1]['content'])
        self.assertEqual(prompt['draft'],self.run['draft'])
        self.assertEqual(prompt['guidance'],messages)
        self.assertEqual(prompt['scope'],self.run['scope'])
        self.assertEqual(result['call']['message_ids'],[m['id'] for m in messages])
        self.assertEqual(result['valid_fact_ids'],['f'*32])
        self.assertEqual(result['observations'],self.observations)
        result['run']['draft']['goal']='changed'
        self.assertEqual(self.run['draft']['goal'],'entire goal')
        self.assertTrue(all(m['status']=='queued' for m in self.store.messages(self.run['id'])))

    def test_prepare_local_failures_do_not_reserve(self):
        for mutation in ('expiry','missing_profile','oversize','foreign_message','stale_message','wrong_kind','invalid_observations'):
            original = copy.deepcopy(self.run)
            args = {}
            if mutation=='expiry': self.run['policy']['expires_at']=time.time()+1
            if mutation=='missing_profile': self.run['draft']['model_profile_id']=None
            if mutation=='oversize': args['observations']=[dict(fact_id='f'*32,valid=True,description='x'*262144,evidence=[])]
            if mutation in ('foreign_message','stale_message','wrong_kind'):
                m=self.store.add_message(self.run['id'],dict(request_id=uuid.uuid4().hex,kind='guidance',text='queued'))
                m.update({'foreign_message':dict(run_id='0'*32),'stale_message':dict(status='consumed'),'wrong_kind':dict(kind='prioritize')}[mutation]); args['guidance']=[m]
            if mutation=='invalid_observations': args['observations']=[dict(fact_id='f'*32,valid=True,description='bad',evidence=[])]
            self.denied(lambda:self.prepare(**args)); self.run=original
        self.assertEqual(self.store.model_calls(self.run['id']),[])

    def test_prepare_role_override_configuration_and_ascii_size_boundaries(self):
        override=self.models.save(dict(name='override',provider='custom',base_url='http://127.0.0.1:9/v1',
            model='role-model',api_key='synthetic-other-key',timeout_seconds=5))
        self.run['draft']['role_profiles']['Scout']=override['id']
        self.assertEqual(self.prepare(role='Scout')['profile']['id'],override['id'])
        before=len(self.store.model_calls(self.run['id']))
        with mock.patch.object(self.models,'get',return_value=dict(self.profile,has_key=False)):
            self.denied(lambda:self.prepare())
        # Raw unicode is small; actual ensure_ascii request serialization crosses
        # the per-message cap. Nothing is silently omitted or budgeted.
        obs=copy.deepcopy(self.observations)*1
        obs[0]['description']='unicode'
        obs[0]['evidence'][0]['excerpt']='\U0001f600'*4096
        self.run['draft']['context']='\U0001f600'*16000
        self.run['draft']['guidance']='\U0001f600'*16000
        self.denied(lambda:self.prepare(observations=obs))
        self.assertEqual(len(self.store.model_calls(self.run['id'])),before)

    def fixture(self):
        self.hits=[]; self.content=json.dumps(self.plan); owner=self
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(self):
                owner.hits.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                self.send_response(200); self.end_headers()
                self.wfile.write(json.dumps(dict(choices=[dict(message=dict(content=owner.content,reasoning_content='private'))],
                    model='synthetic-key',usage=dict(prompt_tokens=1,completion_tokens=2,total_tokens=3))).encode())
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler); server.daemon_threads=False
        thread=threading.Thread(target=server.serve_forever); thread.start()
        self.addCleanup(lambda:(server.shutdown(),server.server_close(),thread.join()))
        data=dict(name='fixture',provider='custom',base_url='http://127.0.0.1:'+str(server.server_port)+'/v1',model='fixture',api_key='synthetic-key',timeout_seconds=5)
        self.profile=self.models.save(data,profile_id=self.profile['id']); return data

    def test_real_model_execute_once_no_store_writes_validated_redacted_metadata(self):
        self.fixture(); prepared=self.prepare()
        result=self.api().execute_call(self.models,prepared)
        self.assertEqual(result['proposal'],self.plan); self.assertEqual(len(self.hits),1)
        self.assertNotIn('synthetic-key',json.dumps(result)); self.assertNotIn('private',json.dumps(result))
        self.assertEqual(self.store.model_calls(self.run['id'])[0]['status'],'reserved')
        self.content=json.dumps(dict(self.plan,approval=True))
        self.denied(lambda:self.api().execute_call(self.models,self.prepare()))
        self.assertEqual(len(self.hits),2)
        self.content='synthetic-key invalid response'
        self.denied(lambda:self.api().execute_call(self.models,self.prepare())); self.assertEqual(len(self.hits),3)

    def test_expected_revision_race_fails_before_fixture_hit(self):
        data=self.fixture(); prepared=self.prepare(); data['name']='changed'
        self.models.save(data,profile_id=self.profile['id'])
        self.denied(lambda:self.api().execute_call(self.models,prepared)); self.assertEqual(self.hits,[])

    def test_consumed_guidance_continues_in_real_provider_context_without_reconsumption(self):
        self.fixture()
        earlier=[]
        for note in ('first operator constraint', 'second operator correction'):
            message=self.store.add_message(self.run['id'],dict(request_id=uuid.uuid4().hex,kind='guidance',text=note))
            prepared=self.prepare(guidance=[message])
            result=self.api().execute_call(self.models,prepared)
            self.store.finish_model_call(self.run['id'],prepared['call']['id'],status='succeeded',result=result)
            earlier.append(self.store.finish_message(self.run['id'],message['id'],status='consumed',
                consumer=prepared['call']['id'],result='applied once'))
        new=self.store.add_message(self.run['id'],dict(request_id=uuid.uuid4().hex,kind='guidance',text='new guidance'))
        unused=self.store.add_message(self.run['id'],dict(request_id=uuid.uuid4().hex,kind='guidance',text='not supplied'))
        failed=self.store.add_message(self.run['id'],dict(request_id=uuid.uuid4().hex,kind='guidance',text='failed guidance'))
        self.store.finish_message(self.run['id'],failed['id'],status='failed',consumer='prior-call',result='failed')
        other=self.store.add_message(self.run['id'],dict(request_id=uuid.uuid4().hex,kind='prioritize',text='not guidance'))
        self.store.finish_message(self.run['id'],other['id'],status='consumed',consumer='controller',result='applied')
        before=self.store.messages(self.run['id'])
        prepared=self.prepare(guidance=[new])
        result=self.api().execute_call(self.models,prepared)
        prompt=json.loads(self.hits[-1]['messages'][1]['content'])
        self.assertIn('history',prompt,'consumed operator guidance is missing from later calls')
        self.assertEqual(prompt['history'],earlier)
        self.assertEqual(prompt['guidance'],[new])
        ids=[m['id'] for m in earlier]
        self.assertEqual(prepared['history_message_ids'],ids)
        self.assertEqual(result['metadata']['history_message_ids'],ids)
        self.assertEqual(prepared['call']['message_ids'],[new['id']])
        self.assertEqual(self.store.model_calls(self.run['id'])[-1]['message_ids'],[new['id']])
        self.assertEqual(self.store.messages(self.run['id']),before)
        self.assertEqual(next(m for m in before if m['id']==unused['id'])['status'],'queued')
        again=self.prepare()
        self.assertEqual(json.loads(again['messages'][1]['content'])['history'],earlier)
        self.assertEqual(again['call']['message_ids'],[])
        self.assertEqual(again['history_message_ids'],ids)
        result['metadata']['history_message_ids'].append('changed')
        self.assertEqual(prepared['history_message_ids'],ids)

    def test_oversized_consumed_history_fails_before_additional_reservation(self):
        messages=[self.store.add_message(self.run['id'],dict(request_id=uuid.uuid4().hex,kind='guidance',text='x'*4000)) for _ in range(70)]
        call=self.store.reserve_model_call(self.run['id'],role='Commander',profile_id=self.profile['id'],
            purpose='guidance',message_ids=[m['id'] for m in messages])
        self.store.finish_model_call(self.run['id'],call['id'],status='succeeded',result={})
        for message in messages:
            self.store.finish_message(self.run['id'],message['id'],status='consumed',consumer=call['id'],result='applied')
        before=self.store.messages(self.run['id'])
        error=self.denied(lambda:self.prepare())
        self.assertIn('大小',str(error))
        self.assertEqual(len(self.store.model_calls(self.run['id'])),1)
        self.assertEqual(self.store.messages(self.run['id']),before)

    def test_stored_history_corruption_rejects_before_reservation(self):
        message=self.store.add_message(self.run['id'],dict(request_id=uuid.uuid4().hex,kind='guidance',text='prior guidance'))
        consumed=self.store.finish_message(self.run['id'],message['id'],status='consumed',consumer='prior-call',result='applied')
        changes=[dict(run_id='0'*32),dict(kind='unknown'),dict(status='unknown'),dict(id='invalid'),
            dict(text='bad\x00text'),dict(consumer=None),dict(result=[]),dict(extra='unknown')]
        for change in changes:
            with self.subTest(change=change):
                # Corrupt a fixture's stored JSON; do not replace the real store reader.
                with sqlite3.connect(self.store.database) as db:
                    db.execute('UPDATE messages SET record=? WHERE id=?',(json.dumps(dict(consumed,**change)),message['id']))
                self.denied(lambda:self.prepare())
                self.assertEqual(self.store.model_calls(self.run['id']),[])

    def test_malformed_stored_history_json_has_safe_workspace_failure(self):
        message=self.store.add_message(self.run['id'],dict(request_id=uuid.uuid4().hex,kind='guidance',text='prior guidance'))
        with sqlite3.connect(self.store.database) as db:
            db.execute('UPDATE messages SET record=? WHERE id=?',('{"text": "synthetic-key',message['id']))
        try:self.denied(lambda:self.prepare())
        except ValueError:self.fail('malformed stored JSON escaped the safe WorkspaceError boundary')
        self.assertEqual(self.store.model_calls(self.run['id']),[])

    def test_execute_analysis_guidance_review_dispatch_and_no_fallback(self):
        self.fixture()
        for purpose in ('analyze','guidance'):
            self.content=json.dumps(dict(summary='data',gaps=[],findings=[self.finding]))
            result=self.api().execute_call(self.models,self.prepare(purpose=purpose,observations=self.observations))
            self.assertEqual(result['proposal']['findings'],[self.finding])
        case=self.review_case(); self.content=json.dumps(dict(summary='advisory',gaps=[],review_suggestions=[]))
        self.assertEqual(self.api().execute_call(self.models,self.prepare(role='General',purpose='review',
            observations=self.observations,findings=[case]))['proposal']['review_suggestions'],[])
        prepared=self.prepare()
        with mock.patch.object(self.models,'complete',side_effect=ModelError('timeout')) as call:
            self.denied(lambda:self.api().execute_call(self.models,prepared)); self.assertEqual(call.call_count,1)

    def test_excerpt_common_secrets_bounded_without_universal_redaction_claim(self):
        source=b'Authorization: Bearer synthetic-key\nCookie: sid=synthetic-cookie\nSet-Cookie: sid=synthetic-set\n{"api_key":"synthetic-api", "password":"synthetic-password", "refresh_token":"synthetic-refresh"}\naccess-token=synthetic-access secret: synthetic-secret opaque=unknown-custom-value'
        excerpt=self.api().response_excerpt(source)
        for secret in ('synthetic-key','synthetic-cookie','synthetic-set','synthetic-api','synthetic-password','synthetic-refresh','synthetic-access','synthetic-secret'):
            self.assertNotIn(secret,excerpt)
        self.assertIn('unknown-custom-value',excerpt)
        self.assertLessEqual(len(self.api().response_excerpt(b'x'*100000)),4096)
        self.assertNotIn('\x00',self.api().response_excerpt(b'bad\xff\x00text'))

    def test_excerpt_cookie_json_text_forms_mask_whole_value_preserving_neighbors(self):
        cases=[
            ('{"Cookie":"sid=synthetic-cookie"}',()),
            ('{"Set-Cookie":"sid=synthetic-cookie; HttpOnly"}',()),
            ('Cookie=sid=synthetic-cookie',()),
            ('{"cOoKiE" : "sid=synthetic-cookie; other=synthetic-other", "note":"visible"}',('"note":"visible"',)),
            ('{"sEt-CoOkIe" = "sid=synthetic-cookie; HttpOnly", "note":"visible"}',('"note":"visible"',)),
            ("'Cookie' = 'sid=synthetic-cookie; other=synthetic-other' next prose",('next prose',)),
            ('Cookie = sid=synthetic-cookie; other=synthetic-other; Path=/\nNext: visible',('Next: visible',)),
            ('Set-Cookie: sid=synthetic-cookie; HttpOnly; Secure\nNext: visible',('Next: visible',)),
            ('before Cookie: sid=synthetic-cookie next prose',('before','next prose')),
            ('Cookie=sid=synthetic-cookie; other=synthetic-other next prose',('next prose',)),
            ('Cookie=sid="synthetic-cookie with space"; other=synthetic-other next prose',('next prose',)),
            (json.dumps(dict(Cookie='sid="synthetic-cookie"; other=synthetic-other',note='visible')),('"note": "visible"',)),
            (json.dumps({'Set-Cookie':'sid="synthetic-cookie"; HttpOnly','note':'visible'}),('"note": "visible"',)),
            ('{"Cookie":"sid=synthetic-cookie", "Set-Cookie":"other=synthetic-other", "note":"visible"}',('"note":"visible"',)),
        ]
        for source,neighbors in cases:
            with self.subTest(source=source):
                excerpt=self.api().response_excerpt(source.encode())
                self.assertNotIn('synthetic-cookie',excerpt)
                self.assertNotIn('synthetic-other',excerpt)
                for neighbor in neighbors:self.assertIn(neighbor,excerpt)
                self.assertLessEqual(len(excerpt),4096)

    def test_excerpt_cookie_value_crossing_inspection_prefix_is_masked(self):
        for key in ('Cookie','Set-Cookie'):
            with self.subTest(key=key):
                source=('{"'+key+'":"sid=synthetic-cookie'+'x'*70000+'"}').encode()
                excerpt=self.api().response_excerpt(source)
                self.assertNotIn('synthetic-cookie',excerpt)
                self.assertLessEqual(len(excerpt),4096)


class DNSTests(unittest.TestCase):
    def api(self):
        try:return importlib.import_module('pentest.dns_resolve')
        except ImportError:self.fail('bounded DNS helper is missing')

    def test_numeric_bypasses_child_and_localhost_real_child(self):
        api=self.api()
        with mock.patch('subprocess.Popen',side_effect=AssertionError('numeric child')):
            self.assertEqual(api.resolve_host('127.0.0.1'),['127.0.0.1'])
            self.assertEqual(api.resolve_host('::1'),['::1'])
        real=subprocess.Popen; children=[]
        def track(*args,**kw):
            self.assertNotIn('HTTP_PROXY',kw['env']); self.assertNotIn('synthetic-key',repr(kw))
            self.assertEqual(args[0][1],'-I'); self.assertTrue(Path(args[0][2]).is_absolute())
            child=real(*args,**kw);children.append(child);return child
        with mock.patch('subprocess.Popen',side_effect=track):
            answers=api.resolve_host('localhost')
        self.assertTrue(answers); self.assertTrue(set(answers)<={'127.0.0.1','::1'})
        self.assertIsNotNone(children[0].poll())

    def child_answer(self,raw):
        real=subprocess.Popen
        def fixture(args,**kw):
            return real([sys.executable,'-I','-c','import sys; sys.stdin.buffer.read(); sys.stdout.buffer.write('+repr(raw)+')'],**kw)
        return mock.patch('subprocess.Popen',side_effect=fixture)

    def test_invalid_inputs_answers_and_bounded_output(self):
        api=self.api()
        for host in ('','a b','a;whoami','-bad','127.1','0.0.0.0','::','::ffff:127.0.0.1','224.0.0.1','ff02::1','a\ud800'):
            with self.assertRaises(WorkspaceError):api.resolve_host(host)
        for answers in ([],['bad'],['0.0.0.0'],['::ffff:127.0.0.1'],['224.0.0.1'],['ff02::1'],['127.0.0.1']*65,{},['127.0.0.1',False]):
            with self.child_answer(json.dumps(answers).encode()):
                with self.assertRaises(WorkspaceError):api.resolve_host('localhost')
        for raw in (b'x'*20000,b'not json',b'["127.0.0.1"] trailing'):
            with self.child_answer(raw):
                with self.assertRaises(WorkspaceError):api.resolve_host('localhost')
        with self.child_answer(b'["127.0.0.1","127.0.0.1"]'):
            self.assertEqual(api.resolve_host('localhost'),['127.0.0.1'])

    def test_whole_call_timeout_kills_and_reaps_blocked_dns_child(self):
        api=self.api();real=subprocess.Popen; children=[]
        def blocked(args,**kw):
            code='import socket,time,runpy; socket.getaddrinfo=lambda *a,**k: time.sleep(60); runpy.run_path('+repr(args[2])+',run_name="__main__")'
            child=real([sys.executable,'-I','-c',code],**kw); children.append(child); return child
        started=time.monotonic()
        with mock.patch('subprocess.Popen',side_effect=blocked):
            with self.assertRaises(WorkspaceError):api.resolve_host('localhost',timeout=.2)
        self.assertLess(time.monotonic()-started,1.5); self.assertIsNotNone(children[0].poll())


if __name__=='__main__':unittest.main()

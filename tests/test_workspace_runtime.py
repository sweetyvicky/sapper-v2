"""Direct protected operator service: real SQLite and isolated loopback targets."""
import http.server
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from pentest.workspace_intake import parse_assets
from pentest.workspace_store import WorkspaceError
try:
    from pentest.workspace import Workspace
except ImportError:
    Workspace = None


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(Workspace, 'protected Workspace service is missing')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'workspace'
        self.hits = []
        self.entered, self.release = threading.Event(), threading.Event()
        owner = self
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                owner.hits.append(self.path)
                if self.path == '/wait':
                    owner.entered.set(); owner.release.wait(3)
                body = b'local observation; Authorization: Bearer synthetic-secret\nCookie: session=synthetic-cookie'
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                try: self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError): pass
            def do_HEAD(self):
                owner.hits.append(self.path)
                self.send_response(200); self.end_headers()
        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.addCleanup(self.cleanup_server)
        self.origin = 'http://127.0.0.1:%s' % self.server.server_port
        self.ws = Workspace(self.root)
        self.addCleanup(self.ws.close)

    def cleanup_server(self):
        self.release.set(); self.server.shutdown(); self.server.server_close(); self.thread.join(3)
        self.assertFalse(self.thread.is_alive())

    def draft(self, paths=('/',), **changes):
        data = dict(name='Local authorized fixture', goal='Observe exact authorized paths',
                    assets=parse_assets('\n'.join(self.origin+p for p in paths))['assets'],
                    allowed_tools=['http_get'], max_request_seconds=4, max_response_bytes=1024)
        data.update(changes)
        return self.ws.store.save_draft(data)

    def prepare(self, paths=('/',), **changes):
        draft = self.draft(paths, **changes)
        run = self.ws.prepare(draft['id'], draft['revision'])
        self.ws.wait(run['id'], timeout=10)
        return self.ws.snapshot(run['id'])

    def approve(self, snap):
        return self.ws.approve(snap['run']['id'], snap['plan']['revision'],
                               [a['id'] for a in snap['plan']['actions'] if a['state']=='pending'], 'operator')

    def execute(self, snap):
        self.approve(snap)
        self.ws.start(snap['run']['id']); self.ws.wait(snap['run']['id'], timeout=10)
        return self.ws.snapshot(snap['run']['id'])

    def test_batch_prepare_and_exact_approval_are_zero_hit_then_real_receipts(self):
        snap = self.prepare(('/', '/two'))
        rid = snap['run']['id']
        self.assertEqual(self.hits, [])
        self.assertEqual(snap['run']['status'], 'awaiting_approval')
        self.assertEqual(len(snap['plan']['actions']), 2)
        self.assertEqual(len(snap['coverage']['assets']), 2)
        self.assertTrue(any(c['method']=='manual' for c in snap['coverage']['checks']))
        with self.assertRaises(WorkspaceError): self.ws.approve(rid, 99, [snap['plan']['actions'][0]['id']], 'operator')
        with self.assertRaises(WorkspaceError): self.ws.approve(rid, 1, ['unknown'], 'operator')
        with self.assertRaises(WorkspaceError): self.ws.approve(rid, 1, [snap['plan']['actions'][0]['id']], '')
        self.approve(snap); self.approve(snap)
        self.assertEqual(self.hits, [])
        self.ws.start(rid); self.ws.wait(rid, timeout=10)
        out = self.ws.snapshot(rid)
        self.assertEqual(out['run']['status'], 'completed')
        self.assertEqual(len(self.hits), 2)
        self.assertEqual(len(out['runtime']['evidence']['facts']), 2)
        self.assertEqual(out['budget']['usage']['requests'], 2)
        self.assertFalse(out['run']['engagement_complete'])
        self.assertEqual({a['state'] for a in out['plan']['actions']}, {'succeeded'})
        self.assertEqual({w['role'] for w in out['runtime']['workers']}, {'Scout','Soldier','General'})
        self.assertEqual(out['runtime']['commander']['state'], 'persistent')
        before = len(self.hits)
        for fmt in ('markdown','html','json'):
            report = self.ws.report(rid, fmt)
            self.assertNotIn('synthetic-secret', report)
            self.assertNotIn('synthetic-cookie', report)
        self.assertEqual(len(self.hits), before)

    def test_pause_has_requested_then_ack_and_resume_no_extra_request(self):
        snap = self.prepare(('/wait', '/two'))
        rid = snap['run']['id']; actions = snap['plan']['actions']
        message = dict(request_id=uuid.uuid4().hex, kind='prioritize', text='first wait',
                       action_ids=[next(a['id'] for a in actions if a['target'].endswith('/wait'))])
        self.assertEqual(self.ws.message(rid,message)['status'], 'consumed')
        self.approve(snap); self.ws.start(rid)
        self.assertTrue(self.entered.wait(5))
        self.assertEqual(self.ws.pause(rid)['status'], 'pause_requested')
        self.release.set(); self.ws.wait(rid,timeout=10)
        self.assertEqual(self.ws.snapshot(rid)['run']['status'], 'paused')
        self.assertEqual(len(self.hits),1)
        self.ws.resume(rid); self.ws.wait(rid,timeout=10)
        self.assertEqual(len(self.hits),2)
        self.assertEqual(self.ws.snapshot(rid)['run']['status'],'completed')

    def test_cancel_revokes_remaining_work_and_never_resumes(self):
        snap=self.prepare(('/wait','/two')); rid=snap['run']['id']
        first=next(a for a in snap['plan']['actions'] if a['target'].endswith('/wait'))
        self.ws.message(rid,dict(request_id=uuid.uuid4().hex,kind='prioritize',text='wait first',action_ids=[first['id']]))
        self.approve(snap); self.ws.start(rid); self.assertTrue(self.entered.wait(5))
        self.assertEqual(self.ws.cancel(rid)['status'],'cancel_requested')
        self.release.set(); self.ws.wait(rid,timeout=10)
        self.assertEqual(self.ws.snapshot(rid)['run']['status'],'cancelled')
        with self.assertRaises(WorkspaceError): self.ws.resume(rid)
        with self.assertRaises(WorkspaceError): self.ws.start(rid)
        self.assertEqual(len(self.hits),1)

    def test_finding_retest_new_approval_independent_review_stale_and_report(self):
        snap=self.execute(self.prepare()); rid=snap['run']['id']
        fact=snap['runtime']['evidence']['facts'][0]
        data=dict(fact_id=fact['id'],title='Candidate fixture observation',severity='low',reporter='operator',
                  description='Description',impact='Impact',reproduction='GET fixture',remediation='Review fixture',cwe='',operator_note='')
        case=self.ws.create_finding(rid,data)
        self.assertEqual(case['status'],'candidate')
        self.assertEqual(case['description'],'Description')
        self.assertNotIn('synthetic-secret',json.dumps(case))
        original=case['evidence'][0]
        with self.assertRaises(WorkspaceError):
            self.ws.review_finding(rid,case['id'],reviewer='reviewer',evidence_id=original['id'],outcome='confirmed',note='same receipt denied')
        msg=dict(request_id=uuid.uuid4().hex,kind='retest',text='Independent test',finding_id=case['id'])
        applied=self.ws.message(rid,msg)
        self.assertEqual(applied['status'],'consumed')
        self.assertEqual(self.ws.message(rid,msg),applied)
        snap=self.ws.snapshot(rid)
        self.assertEqual(len(snap['plan']['actions']),2)
        self.assertEqual(len(self.hits),1)
        self.approve(snap); self.ws.start(rid); self.ws.wait(rid,timeout=10)
        after=self.ws.snapshot(rid)
        evidence=next(e for e in after['runtime']['evidence']['evidence'] if e['id']!=original['id'])
        case=self.ws.review_finding(rid,case['id'],reviewer='independent-reviewer',evidence_id=evidence['id'],outcome='confirmed',note='Independent fixture')
        self.assertEqual(case['status'],'confirmed')
        self.ws.invalidate_fact(rid,fact['id'],actor='operator',reason='Withdraw fixture claim')
        self.assertEqual(self.ws.finding(rid,case['id'])['status'],'stale')
        report=json.loads(self.ws.report(rid,'json'))
        self.assertEqual(report['findings'][0]['status'],'stale')
        self.assertEqual(report['budget']['usage']['requests'],2)

    def test_recorded_only_guidance_exclusive_root_and_restart_no_replay(self):
        snap=self.prepare(); rid=snap['run']['id']; self.approve(snap)
        msg=dict(request_id=uuid.uuid4().hex,kind='guidance',text='Check application login carefully')
        result=self.ws.message(rid,msg)
        self.assertEqual(result['consumer'],'operator-record')
        self.assertEqual(result['status'],'consumed')
        with self.assertRaises(WorkspaceError): Workspace(self.root)
        self.ws.close()
        self.ws=Workspace(self.root); self.addCleanup(self.ws.close)
        self.assertEqual(self.hits,[])
        self.assertEqual(self.ws.snapshot(rid)['messages'][0],result)
        self.ws.start(rid); self.ws.wait(rid,timeout=10)
        self.assertEqual(len(self.hits),1)

    def test_request_budget_is_persistent_and_never_refunded(self):
        snap=self.prepare(('/', '/two'),budgets=dict(requests=1))
        rid=snap['run']['id']; self.approve(snap); self.ws.start(rid); self.ws.wait(rid,timeout=10)
        after=self.ws.snapshot(rid)
        self.assertEqual(len(self.hits),1)
        self.assertEqual(after['run']['status'],'blocked')
        self.assertEqual(after['budget']['usage']['requests'],1)
        with self.assertRaises(WorkspaceError): self.ws.resume(rid)
        self.assertEqual(len(self.hits),1)


    def model_fixture(self):
        from pentest.models import ModelProfiles
        self.model_requests=[]; self.model_mode='ok'; self.propose_findings=False
        self.model_entered,self.model_release=threading.Event(),threading.Event()
        owner=self
        class ModelHandler(http.server.BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(self):
                payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                context=json.loads(payload['messages'][-1]['content'])
                owner.model_requests.append((payload,context))
                if owner.model_mode=='wait_plan' and context['purpose']=='plan':
                    owner.model_entered.set(); owner.model_release.wait(3)
                if owner.model_mode=='wait_analysis' and context['purpose']=='analyze':
                    owner.model_entered.set(); owner.model_release.wait(3)
                if owner.model_mode=='error' or (owner.model_mode=='analysis_error' and context['purpose']=='analyze'):
                    self.send_response(429); self.end_headers(); return
                if owner.model_mode=='timeout':
                    owner.model_entered.set(); owner.model_release.wait(6)
                if context['purpose']=='plan':
                    asset=context['draft']['assets'][0]
                    target=owner.origin+'/new' if context['guidance'] else asset['target']
                    proposal=dict(summary='Fixture plan',gaps=['Manual assessment remains'],actions=[dict(asset_id=asset['id'],target=target,tool='http_get',role='Scout',description='Fixture observation',risk=2,evidence_gap=1)])
                    if owner.model_mode=='outside': proposal['actions'][0]['target']='http://192.0.2.2:80/'
                    if owner.model_mode=='unknown': proposal['actions'][0]['approval']='fake'
                elif context['purpose']=='review':
                    case=context['findings'][0]
                    original={e['id'] for e in case['evidence']}
                    fresh=next(e for o in context['observations'] if o['valid'] for e in o['evidence'] if e['id'] not in original)
                    proposal=dict(summary='Independent observation recommendation',gaps=[],review_suggestions=[dict(finding_id=case['id'],evidence_id=fresh['id'],outcome='confirmed',note='Advisory only; operator must review')])
                else:
                    findings=[]
                    if owner.propose_findings:
                        fact=context['observations'][-1]
                        findings=[dict(fact_id=fact['fact_id'],title='Model candidate',severity='low',description='Description',impact='Impact',reproduction='GET fixture',remediation='Review fixture',cwe='',operator_note='')]
                    proposal=dict(summary='Observed fixture',gaps=['Manual assessment remains'],findings=findings)
                    if owner.model_mode=='oversized_analysis': proposal['gaps']=['g'*1024]*100
                    if owner.model_mode=='foreign_fact':
                        proposal['findings']=[dict(fact_id='f'*32,title='Bad',severity='low',description='d',impact='i',reproduction='r',remediation='m',cwe='',operator_note='')]
                raw=json.dumps(dict(choices=[dict(message=dict(content=json.dumps(proposal),reasoning_content='private-chain'))],model=payload['model'],usage=dict(prompt_tokens=1,completion_tokens=1,total_tokens=2))).encode()
                self.send_response(200); self.send_header('Content-Length',str(len(raw))); self.end_headers()
                try: self.wfile.write(raw)
                except (BrokenPipeError,ConnectionResetError): pass
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),ModelHandler)
        thread=threading.Thread(target=server.serve_forever); thread.start()
        def cleanup():
            self.model_release.set(); server.shutdown(); server.server_close(); thread.join(3)
        self.addCleanup(cleanup)
        self.ws.close()
        profiles=ModelProfiles(Path(self.tmp.name)/'profiles',allow_http_loopback=True)
        def profile(name):
            return profiles.save(dict(name=name,provider='custom',base_url='http://127.0.0.1:%s/v1'%server.server_port,
                                      model=name,api_key='synthetic-key',timeout_seconds=5))
        self.default_profile=profile('commander-model'); self.scout_profile=profile('scout-model'); self.general_profile=profile('general-model')
        self.ws=Workspace(self.root,models=profiles); self.addCleanup(self.ws.close)
        return dict(model_profile_id=self.default_profile['id'],role_profiles=dict(Scout=self.scout_profile['id'],General=self.general_profile['id']))

    def test_actual_model_plan_candidate_general_recommendation_and_history(self):
        config=self.model_fixture(); self.propose_findings=True
        snap=self.prepare(**config); rid=snap['run']['id']
        self.assertEqual(len(self.model_requests),1); self.assertEqual(self.hits,[])
        snap=self.execute(snap)
        self.assertEqual([c['role'] for c in snap['model_calls']],['Commander','Scout'])
        self.assertEqual(snap['model_calls'][1]['result']['profile']['id'],self.scout_profile['id'])
        self.assertEqual(snap['model_calls'][1]['result']['profile']['revision'],1)
        self.assertEqual(len(snap['findings']),1); case=snap['findings'][0]
        self.assertEqual(case['status'],'candidate')
        msg=dict(request_id=uuid.uuid4().hex,kind='retest',text='Independent review',finding_id=case['id'])
        self.assertEqual(self.ws.message(rid,msg)['status'],'consumed')
        self.assertEqual(len(self.hits),1)
        snap=self.execute(self.ws.snapshot(rid))
        self.assertEqual(snap['model_calls'][-1]['role'],'General')
        self.assertEqual(snap['model_calls'][-1]['purpose'],'review')
        self.assertEqual(snap['findings'][0]['status'],'candidate')
        self.assertEqual(len(snap['findings']),1)
        advice=snap['review_suggestions'][0]
        self.assertEqual(advice['state'],'suggested')
        self.assertEqual(advice['current_finding_status'],'candidate')
        self.assertEqual(self.ws.review_finding(rid,case['id'],reviewer='independent',evidence_id=advice['evidence_id'],outcome='confirmed',note='Human reviewed independently')['status'],'confirmed')
        self.assertNotIn('synthetic-key',json.dumps(snap)); self.assertNotIn('private-chain',json.dumps(snap))

    def test_guidance_proposes_pending_path_with_fact_dependency_and_history(self):
        config=self.model_fixture(); snap=self.execute(self.prepare(**config)); rid=snap['run']['id']
        basis=snap['runtime']['evidence']['facts'][0]['id']
        msg=dict(request_id=uuid.uuid4().hex,kind='guidance',text='Please observe /new based on this response')
        queued=self.ws.message(rid,msg); self.ws.wait(rid,timeout=10)
        snap=self.ws.snapshot(rid)
        self.assertEqual(snap['messages'][0]['status'],'consumed')
        self.assertEqual(self.ws.message(rid,msg)['id'],queued['id'])
        self.assertEqual(len(self.hits),1)
        action=snap['plan']['actions'][-1]
        self.assertEqual(action['target'],self.origin+'/new'); self.assertEqual(action['state'],'pending')
        self.assertEqual(action['depends_on'],[basis])
        self.assertEqual(len(snap['coverage']['assets']),2)
        self.assertEqual(self.model_requests[-1][1]['guidance'][0]['text'],msg['text'])
        self.approve(snap); self.ws.start(rid); self.ws.wait(rid,timeout=10)
        self.assertEqual(len(self.hits),2)
        context=self.model_requests[-1][1]
        self.assertEqual(context['history'][0]['id'],queued['id'])
        self.assertEqual(self.ws.snapshot(rid)['model_calls'][-1]['result']['history_message_ids'],[queued['id']])
        again=dict(request_id=uuid.uuid4().hex,kind='guidance',text='Observe /new again')
        self.ws.message(rid,again); self.ws.wait(rid,timeout=10)
        snap=self.ws.snapshot(rid); self.approve(snap)
        self.ws.invalidate_fact(rid,basis,actor='operator',reason='Withdraw basis')
        with self.assertRaises(WorkspaceError): self.ws.start(rid)
        self.assertEqual(len(self.hits),2)

    def test_guidance_during_analysis_waits_for_real_planning_consumer(self):
        config=self.model_fixture(); snap=self.prepare(**config); rid=snap['run']['id']
        self.model_mode='wait_analysis'; self.approve(snap); self.ws.start(rid)
        self.assertTrue(self.model_entered.wait(5))
        msg=dict(request_id=uuid.uuid4().hex,kind='guidance',text='Please test /new next')
        queued=self.ws.message(rid,msg)
        self.assertEqual(queued['status'],'queued')
        self.model_release.set(); self.ws.wait(rid,timeout=10)
        snap=self.ws.snapshot(rid)
        call=next(c for c in snap['model_calls'] if queued['id'] in c['message_ids'])
        self.assertEqual(call['purpose'],'plan')
        self.assertEqual(snap['plan']['actions'][-1]['state'],'pending')
        self.assertEqual(len(self.hits),1)

    def test_initial_model_error_explicit_resume_then_analysis_retry_no_target_replay(self):
        config=self.model_fixture(); self.model_mode='error'
        snap=self.prepare(**config); rid=snap['run']['id']
        self.assertEqual(snap['run']['status'],'blocked'); self.assertIsNone(snap['plan'])
        self.assertEqual(snap['model_calls'][0]['status'],'failed'); self.assertEqual(self.hits,[])
        self.model_mode='ok'; self.ws.resume(rid); self.ws.wait(rid,timeout=10)
        snap=self.ws.snapshot(rid); self.assertEqual(snap['run']['status'],'awaiting_approval',snap['run']['stop_reason'])
        self.model_mode='analysis_error'; self.approve(snap); self.ws.start(rid); self.ws.wait(rid,timeout=10)
        snap=self.ws.snapshot(rid); self.assertEqual(snap['run']['status'],'blocked'); self.assertEqual(len(self.hits),1)
        self.model_mode='ok'; self.ws.resume(rid); self.ws.wait(rid,timeout=10)
        snap=self.ws.snapshot(rid)
        self.assertEqual(snap['run']['status'],'completed'); self.assertEqual(len(self.hits),1)
        self.assertEqual(len(snap['model_calls']),4)
        self.assertEqual(snap['budget']['usage']['requests'],1)

    def test_model_invalid_proposal_budget_and_foreign_fact_fail_without_fallback(self):
        config=self.model_fixture()
        for mode in ('outside','unknown'):
            self.model_mode=mode; snap=self.prepare(**config)
            self.assertEqual(snap['run']['status'],'blocked'); self.assertIsNone(snap['plan'])
            self.assertEqual(snap['model_calls'][0]['status'],'failed')
        self.assertEqual(self.hits,[])
        self.model_mode='ok'; snap=self.prepare(**config,budgets=dict(model_calls=1)); rid=snap['run']['id']
        self.approve(snap); self.ws.start(rid); self.ws.wait(rid,timeout=10)
        after=self.ws.snapshot(rid)
        self.assertEqual(after['run']['status'],'blocked'); self.assertEqual(len(after['model_calls']),1)
        self.assertEqual(len(self.hits),1)
        self.model_mode='foreign_fact'; snap=self.prepare(**config); rid=snap['run']['id']
        self.approve(snap); self.ws.start(rid); self.ws.wait(rid,timeout=10)
        after=self.ws.snapshot(rid)
        self.assertEqual(after['run']['status'],'blocked'); self.assertEqual(after['findings'],[])

    def test_preflight_pins_all_answers_denies_mixed_and_skips_exclusions(self):
        calls=[]
        def resolver(host,*,timeout):
            calls.append(host); return ['127.0.0.1','::1']
        self.ws.close(); self.ws=Workspace(self.root,resolver=resolver); self.addCleanup(self.ws.close)
        draft=self.ws.store.save_draft(dict(name='DNS fixture',goal='Pin only',assets=parse_assets('http://fixture.invalid:%s/'%self.server.server_port+'\nhttp://excluded.invalid:80/') ['assets'],exclusions=['http://excluded.invalid:80'],allowed_tools=['http_get']))
        run=self.ws.prepare(draft['id'],1); self.ws.wait(run['id'],timeout=10)
        snap=self.ws.snapshot(run['id']); self.assertEqual(calls,['fixture.invalid'])
        self.assertEqual(snap['scope']['pinned']['fixture.invalid'],['127.0.0.1','::1'])
        self.assertEqual(len(snap['coverage']['assets']),2)
        snap=self.execute(snap); self.assertEqual(len(self.hits),1)
        draft=self.ws.store.save_draft(dict(name='DNS rejected',goal='Reject mixed denied answer',assets=parse_assets('http://fixture.invalid:80/')['assets'],exclusions=['::1/128']))
        run=self.ws.prepare(draft['id'],1); self.ws.wait(run['id'],timeout=10)
        self.assertEqual(self.ws.snapshot(run['id'])['run']['status'],'blocked')
        self.assertEqual(len(self.hits),1)

    def test_restart_reserved_model_is_uncertain_and_no_automatic_replay(self):
        config=self.model_fixture(); snap=self.prepare(**config); rid=snap['run']['id']
        msg=self.ws.store.add_message(rid,dict(request_id=uuid.uuid4().hex,kind='guidance',text='Uncertain instruction'))
        call=self.ws.store.reserve_model_call(rid,role='Commander',profile_id=self.default_profile['id'],purpose='plan',message_ids=[msg['id']])
        self.ws.close(); self.ws=Workspace(self.root,models=self.ws.models); self.addCleanup(self.ws.close)
        snap=self.ws.snapshot(rid)
        self.assertEqual(snap['run']['status'],'needs_attention')
        self.assertEqual(snap['model_calls'][-1]['status'],'uncertain')
        self.assertEqual(snap['messages'][0]['status'],'queued')
        with self.assertRaises(WorkspaceError): self.ws.resume(rid)
        self.assertEqual(len(self.model_requests),1); self.assertEqual(self.hits,[])

    def test_snapshot_is_side_effect_free_and_corrupt_receipt_is_safe_error(self):
        import hashlib,sqlite3
        from contextlib import closing
        snap=self.execute(self.prepare()); rid=snap['run']['id']
        def inventory():
            return {str(p.relative_to(self.root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.rglob('*') if p.is_file()}
        before=inventory(); self.ws.snapshot(rid); self.ws.report(rid,'json'); self.assertEqual(inventory(),before)
        ledger=self.ws.store.campaign_path(rid)/'ledger.sqlite'
        with closing(sqlite3.connect(ledger)) as db,db: db.execute("UPDATE executions SET body=?",(b'corrupted',))
        with self.assertRaises(WorkspaceError) as error: self.ws.snapshot(rid)
        self.assertNotIn('corrupted',str(error.exception))


    def test_guidance_queued_during_target_must_not_be_consumed_by_analysis(self):
        config=self.model_fixture(); snap=self.prepare(('/wait',),**config); rid=snap['run']['id']
        self.approve(snap); self.ws.start(rid); self.assertTrue(self.entered.wait(5))
        msg=self.ws.message(rid,dict(request_id=uuid.uuid4().hex,kind='guidance',text='Please test /new after wait'))
        self.release.set(); self.ws.wait(rid,timeout=10)
        snap=self.ws.snapshot(rid)
        consumer=next(c for c in snap['model_calls'] if c['id']==snap['messages'][0]['consumer'])
        self.assertEqual(consumer['purpose'],'plan')
        self.assertEqual(snap['plan']['actions'][-1]['target'],self.origin+'/new')
        self.assertEqual(len(self.hits),1)

    def test_pause_during_idle_guidance_job_is_acknowledged_without_dispatch(self):
        config=self.model_fixture(); snap=self.execute(self.prepare(**config)); rid=snap['run']['id']
        self.model_mode='wait_plan'
        self.ws.message(rid,dict(request_id=uuid.uuid4().hex,kind='guidance',text='Observe /new after pause'))
        self.assertTrue(self.model_entered.wait(5))
        self.assertEqual(self.ws.pause(rid)['status'],'pause_requested')
        self.model_release.set(); self.ws.wait(rid,timeout=10)
        self.assertEqual(self.ws.snapshot(rid)['run']['status'],'paused')
        self.assertEqual(len(self.hits),1)

    def test_start_closed_workspace_and_cancelled_approval_repeat_denied(self):
        snap=self.prepare(); rid=snap['run']['id']; self.approve(snap)
        self.ws.cancel(rid)
        with self.assertRaises(WorkspaceError): self.approve(snap)
        self.ws.close()
        with self.assertRaises(WorkspaceError): self.ws.message(rid,dict(request_id=uuid.uuid4().hex,kind='guidance',text='closed'))

    def test_model_context_size_failure_is_visible_and_message_not_forever_queued(self):
        config=self.model_fixture(); snap=self.prepare(**config); rid=snap['run']['id']
        for i in range(70):
            msg=self.ws.store.add_message(rid,dict(request_id=uuid.uuid4().hex,kind='guidance',text='x'*4000))
            self.ws.store.finish_message(rid,msg['id'],status='consumed',consumer='fixture-history',result='Recorded historical context')
        msg=self.ws.message(rid,dict(request_id=uuid.uuid4().hex,kind='guidance',text='new request'))
        self.ws.wait(rid,timeout=10); after=self.ws.snapshot(rid)
        self.assertEqual(after['messages'][-1]['status'],'failed')
        self.assertEqual(after['run']['status'],'blocked')
        self.assertEqual(len(self.model_requests),1)
        self.assertEqual(len(after['model_calls']),1)


    def interrupted_execution(self, *, terminal):
        import sqlite3
        from contextlib import closing
        from pentest import workspace_runner as runner
        snap=self.prepare(('/', '/two')); rid=snap['run']['id']; self.approve(snap)
        run=self.ws.store.get_run(rid); item=run['plan']['actions'][0]
        current=runner.campaign(self.ws.store,run)
        current.apply_proposals([runner.task(item)])
        if terminal:
            receipt=current.broker.execute(runner.action_object(item),item['approval_id'])
        else:
            receipt=current.ledger.reserve(runner.action_object(item),item['approval_id'])
        with closing(sqlite3.connect(current.path)) as db,db:
            db.execute("UPDATE tasks SET state='running',worker_id='scout',approval_id=?,lease_until=? WHERE id=?",(item['approval_id'],time.time()+100,item['id']))
            db.execute("UPDATE workers SET state='running',task_id=? WHERE id='scout'",(item['id'],))
        run=self.ws.store.get_run(rid)
        self.ws.store.update_run(rid,dict(status='running'),expected_revision=run['revision'])
        self.ws.close(); self.ws=Workspace(self.root); self.addCleanup(self.ws.close)
        return rid,item

    def test_restart_reconciles_terminal_receipt_then_only_remaining_action(self):
        rid,item=self.interrupted_execution(terminal=True)
        self.assertEqual(self.ws.snapshot(rid)['run']['status'],'needs_attention')
        self.assertEqual(len(self.hits),1)
        self.ws.resume(rid); self.ws.wait(rid,timeout=10)
        snap=self.ws.snapshot(rid)
        self.assertEqual(snap['run']['status'],'completed')
        self.assertEqual(len(self.hits),2)
        self.assertEqual(len(snap['runtime']['evidence']['facts']),2)

    def test_restart_pending_execution_blocks_until_known_without_replay(self):
        rid,item=self.interrupted_execution(terminal=False)
        with self.assertRaises(WorkspaceError): self.ws.resume(rid)
        self.assertEqual(self.hits,[])
        self.assertEqual(self.ws.snapshot(rid)['budget']['usage']['requests'],1)

    def test_preflight_expiry_is_bound_to_creation_not_dns_completion(self):
        now=[time.time()]
        def resolver(host,*,timeout): now[0]+=10; return ['127.0.0.1']
        self.ws.close(); self.ws=Workspace(self.root,resolver=resolver,clock=lambda:now[0]); self.addCleanup(self.ws.close)
        draft=self.ws.store.save_draft(dict(name='DNS time',goal='Bound expiry',assets=parse_assets('http://fixture.invalid:80/')['assets'],expiry_seconds=60))
        run=self.ws.prepare(draft['id'],1); self.ws.wait(run['id'],timeout=10)
        snap=self.ws.snapshot(run['id'])
        self.assertEqual(snap['policy']['expires_at'],run['created_at']+60)

    def test_no_model_manual_assessment_and_narrative_optimistic_update(self):
        snap=self.execute(self.prepare()); rid=snap['run']['id']; fact=snap['runtime']['evidence']['facts'][0]
        case=self.ws.create_finding(rid,dict(fact_id=fact['id'],title='Case',severity='info',reporter='operator',description='D',impact='I',reproduction='R',remediation='M',cwe='',operator_note=''))
        details=dict(description='Updated',impact='I',reproduction='R',remediation='M',cwe='',operator_note='')
        case=self.ws.update_finding(rid,case['id'],details,case['narrative_revision'])
        self.assertEqual(case['description'],'Updated'); self.assertEqual(case['narrative_revision'],2)
        with self.assertRaises(WorkspaceError): self.ws.update_finding(rid,case['id'],details,1)
        aid=snap['draft']['assets'][0]['id']
        self.ws.assess_coverage(rid,asset_id=aid,check_id='manual',outcome='completed',actor='reviewer',note='Manual fixture assessment',fact_ids=[fact['id']])
        self.assertEqual(next(c for c in self.ws.snapshot(rid)['coverage']['cells'] if c['check_id']=='manual')['state'],'covered')


    def test_partial_narrative_storage_failure_is_visible_and_needs_attention(self):
        from unittest import mock
        config=self.model_fixture(); self.propose_findings=True
        snap=self.prepare(**config); rid=snap['run']['id']; self.approve(snap)
        with mock.patch.object(self.ws.store,'save_narrative',side_effect=WorkspaceError('storage','Safe fixture storage failure')):
            self.ws.start(rid); self.ws.wait(rid,timeout=10)
        snap=self.ws.snapshot(rid)
        self.assertEqual(snap['run']['status'],'needs_attention')
        self.assertEqual(len(snap['findings']),1)
        self.assertTrue(snap['findings'][0]['narrative_incomplete'])
        self.assertEqual(snap['findings'][0]['status'],'candidate')
        with self.assertRaises(WorkspaceError): self.ws.resume(rid)

    def test_oversized_analysis_result_has_no_partial_candidate_effect(self):
        config=self.model_fixture(); self.propose_findings=True
        snap=self.prepare(**config); rid=snap['run']['id']
        self.model_mode='oversized_analysis'; self.approve(snap); self.ws.start(rid); self.ws.wait(rid,timeout=10)
        snap=self.ws.snapshot(rid)
        self.assertEqual(snap['run']['status'],'blocked')
        self.assertEqual(snap['findings'],[])
        self.assertEqual(snap['model_calls'][-1]['status'],'failed')
        self.assertEqual(len(self.hits),1)

    def test_model_whole_call_timeout_is_charged_and_has_no_fallback(self):
        config=self.model_fixture(); self.model_mode='timeout'
        snap=self.prepare(**config)
        self.assertEqual(snap['run']['status'],'blocked')
        self.assertEqual(snap['model_calls'][0]['status'],'failed')
        self.assertIsNone(snap['plan']); self.assertEqual(self.hits,[])
        self.assertEqual(len(self.model_requests),1)

    def test_max_active_rejects_before_creating_unmanaged_run(self):
        config=self.model_fixture(); self.model_mode='wait_plan'
        draft=self.draft(**config)
        one=self.ws.prepare(draft['id'],1); two=self.ws.prepare(draft['id'],1)
        self.assertTrue(self.model_entered.wait(5))
        with self.assertRaises(WorkspaceError): self.ws.prepare(draft['id'],1)
        self.assertEqual(len(self.ws.store.list_runs()),2)
        self.model_release.set(); self.ws.wait(one['id'],timeout=10); self.ws.wait(two['id'],timeout=10)
        self.assertEqual(self.hits,[])

    def test_advice_exposes_current_evidence_validity_after_fact_invalidation(self):
        config=self.model_fixture(); self.propose_findings=True
        snap=self.execute(self.prepare(**config)); rid=snap['run']['id']; case=snap['findings'][0]
        self.ws.message(rid,dict(request_id=uuid.uuid4().hex,kind='retest',text='Review independently',finding_id=case['id']))
        snap=self.execute(self.ws.snapshot(rid)); advice=snap['review_suggestions'][0]
        self.assertTrue(advice['evidence_current_valid'])
        fact=next(f for f in snap['runtime']['evidence']['facts'] if advice['evidence_id'] in f['evidence_ids'])
        self.ws.invalidate_fact(rid,fact['id'],actor='operator',reason='Withdraw independent observation')
        self.assertFalse(self.ws.snapshot(rid)['review_suggestions'][0]['evidence_current_valid'])
        self.assertEqual(self.ws.finding(rid,case['id'])['status'],'candidate')


    def test_unsent_guidance_has_explicit_failure_when_job_stops_on_model_error(self):
        config=self.model_fixture(); snap=self.prepare(('/wait',),**config); rid=snap['run']['id']
        self.model_mode='analysis_error'; self.approve(snap); self.ws.start(rid)
        self.assertTrue(self.entered.wait(5))
        self.ws.message(rid,dict(request_id=uuid.uuid4().hex,kind='guidance',text='Plan /new after observation'))
        self.release.set(); self.ws.wait(rid,timeout=10)
        snap=self.ws.snapshot(rid)
        self.assertEqual(snap['messages'][0]['status'],'failed')
        self.assertEqual(snap['messages'][0]['consumer'],'controller')
        self.assertEqual(len(self.hits),1)


    def test_missing_campaign_snapshot_does_not_recreate_parent_directories(self):
        import shutil
        snap=self.prepare(); rid=snap['run']['id']
        path=self.ws.store.campaign_path(rid).parent
        shutil.rmtree(path)
        with self.assertRaises(WorkspaceError): self.ws.snapshot(rid)
        self.assertFalse(path.exists(),'read-only snapshot recreated a missing campaign parent')


if __name__=='__main__': unittest.main()

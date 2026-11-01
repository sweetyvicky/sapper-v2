"""Offline workspace contracts: real SQLite, no target or model calls."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))

class WorkspaceTests(unittest.TestCase):
    def api(self):
        try:
            from pentest.workspace_store import WorkspaceStore, WorkspaceError
            from pentest.workspace_intake import parse_assets, validate_draft
            from pentest.workspace_reports import render_report
        except ImportError:
            self.fail('Workspace intake/store/report contracts are missing')
        return WorkspaceStore, WorkspaceError, parse_assets, validate_draft, render_report

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def draft(self):
        _, _, parse, validate, _ = self.api()
        return validate(dict(name='任务', goal='观察', assets=parse('example.test')['assets']))

    def run_record(self):
        Store, *_ = self.api()
        store = Store(self.root)
        draft = store.save_draft(self.draft())
        return store, draft, store.create_run(draft['id'], 1)

    def test_intake_csv_dedup_no_dns_and_errors(self):
        _, Error, parse, validate, _ = self.api()
        with patch.object(socket, 'getaddrinfo', side_effect=AssertionError('DNS forbidden')):
            result = parse('target,name,notes\nExample.test,first,"a\nb"\nhttps://example.test/,second,z\nhttp://user:pass@example.test/,bad,z\n', 'csv')
            self.assertEqual(result['counts'], dict(rows=3, valid=1, invalid=1, duplicates=1))
            self.assertEqual(result['assets'][0]['target'], 'https://example.test:443/')
            self.assertEqual(result['assets'][0]['name'], 'first')
            self.assertTrue(result['assets'][0]['assumed_scheme'])
            self.assertEqual(result['duplicates'][0]['first_row'], 2)
            self.assertEqual(len(validate(self.draft())['assets']), 1)
        for text in ('target,target\na,b', 'target,unknown\na,b', 'target,name\na,"unterminated'):
            with self.assertRaises(Error): parse(text, 'csv')
        for target in ('127.1', '0x7f000001', '*.test', 'https://a/#x', 'https://a/a b', '10.0.0.0/24', 'a:b:c'):
            self.assertEqual(parse(target)['counts']['invalid'], 1, target)
        self.assertEqual(parse('::1')['assets'][0]['target'], 'https://[::1]:443/')

    def test_draft_strict_bounds(self):
        _, Error, parse, validate, _ = self.api()
        baseline = self.draft()
        for patch_data in ({'unknown': 1}, {'name': ''}, {'budgets': {'requests': True}}, {'expiry_seconds': 59}, {'role_profiles': {'root': str(uuid.uuid4())}}, {'exclusions': ['https://a/path']}, {'context': '\x00'}, {'assets': baseline['assets'] * 2}):
            with self.assertRaises(Error): validate(dict(baseline, **patch_data))
        self.assertEqual(validate(dict(baseline, exclusions=['https://example.test', '10.0.0.0/24']))['exclusions'][0], 'https://example.test:443')
        self.assertEqual(validate(dict(baseline, allowed_tools=[]))['allowed_tools'], [])
        with self.assertRaises(Error): parse('x' * (1024 * 1024 + 1))
        with self.assertRaises(Error): parse('\n'.join('a.test' for _ in range(501)))

    def test_durable_snapshots_revision_concurrency_and_paths(self):
        Store, Error, *_ = self.api()
        store, draft, run = self.run_record()
        self.assertFalse(store.campaign_path(run['id']).exists())
        self.assertTrue(store.campaign_path(run['id']).parent.exists())
        def update(i):
            try: return Store(self.root).save_draft(dict(self.draft(), goal=str(i)), draft_id=draft['id'], expected_revision=1)
            except Error: return None
        with ThreadPoolExecutor(2) as pool: results = list(pool.map(update, [1, 2]))
        self.assertEqual(sum(x is not None for x in results), 1)
        self.assertEqual(Store(self.root).get_run(run['id'])['draft']['goal'], '观察')
        self.assertNotIn('assets', store.list_drafts()[0])
        self.assertNotIn('draft', store.list_runs()[0])
        for bad in ('../escape', uuid.uuid4().hex, str(uuid.uuid4())):
            with self.assertRaises(Error): store.campaign_path(bad)
        path = store.campaign_path(run['id'])
        path.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(Error): store.campaign_path(run['id'])
        with self.assertRaises(Error): store.update_run(run['id'], {'engagement_complete': True}, expected_revision=1)
        updated = store.update_run(run['id'], {'status': 'awaiting_approval', 'plan': {'x': 1}}, expected_revision=1)
        self.assertEqual(updated['revision'], 2)
        with self.assertRaises(Error): store.update_run(run['id'], {'status': 'failed'}, expected_revision=1)

    def test_events_messages_history_and_terminal_idempotency(self):
        Store, Error, *_ = self.api()
        store, _, run = self.run_record(); rid = run['id']
        event = store.append_event(rid, 'saved', {'ok': True})
        self.assertEqual(store.events(rid), [event])
        self.assertEqual(store.events(rid, after=event['sequence']), [])
        data = dict(request_id=uuid.uuid4().hex, kind='guidance', text='关注响应', action_ids=[], finding_id=None)
        msg = store.add_message(rid, data)
        self.assertEqual(Store(self.root).add_message(rid, data), msg)
        with self.assertRaises(Error): store.add_message(rid, dict(data, text='different'))
        done = store.finish_message(rid, msg['id'], status='consumed', consumer='plan:1', result='已采用')
        self.assertEqual(store.finish_message(rid, msg['id'], status='consumed', consumer='plan:1', result='已采用'), done)
        with self.assertRaises(Error): store.finish_message(rid, msg['id'], status='failed', consumer='plan:1', result='x')
        fid = uuid.uuid4().hex
        narrative = dict(description='描述', impact='影响', reproduction='复现', remediation='建议')
        first = store.save_narrative(rid, fid, narrative)
        store.save_narrative(rid, fid, dict(narrative, impact='新影响'), expected_revision=1)
        self.assertEqual(len(Store(self.root).narrative_history(rid, fid)), 2)
        self.assertEqual(store.narratives(rid)[fid]['revision'], 2)
        with self.assertRaises(Error): store.save_narrative(rid, fid, narrative)
        with self.assertRaises(Error): store.append_event(rid, 'bad', {'x': float('nan')})

    def test_atomic_model_budget_and_queued_messages(self):
        Store, Error, *_ = self.api()
        store = Store(self.root)
        data = self.draft(); data['budgets']['model_calls'] = 1
        draft = store.save_draft(data); rid = store.create_run(draft['id'], 1)['id']
        pid = str(uuid.uuid4())
        def reserve(i):
            try: return Store(self.root).reserve_model_call(rid, role='Commander', profile_id=pid, purpose='plan')
            except Error: return None
        with ThreadPoolExecutor(2) as pool: results = list(pool.map(reserve, [1, 2]))
        self.assertEqual(sum(x is not None for x in results), 1)
        call = next(x for x in results if x)
        self.assertEqual(store.finish_model_call(rid, call['id'], status='uncertain', result={'reason':'restart'})['status'], 'uncertain')
        with self.assertRaises(Error): reserve_result = store.reserve_model_call(rid, role='Commander', profile_id=pid, purpose='plan')
        self.assertEqual(len(Store(self.root).model_calls(rid)), 1)

    def test_report_escapes_evidence_reviews_stale_and_unfinished(self):
        *_, render = self.api()
        snapshot = dict(version=1, generated_at='2026-11-01', task={'id':'t','name':'<script>x</script>','goal':'观察'}, run={'id':'r','status':'paused','stop_reason':'limit','engagement_complete':False}, budget={'limits':{},'usage':{},'model_calls':[{'status':'uncertain'}]}, coverage={'metrics':{},'assets':[],'checks':[],'cells':[{'status':'untested','check':'headers'}]}, findings=[{'id':'f','title':'案例','status':'stale','severity':'low','evidence':[{'id':'e','receipt_id':'receipt','body_sha256':'abc123','excerpt':'```<script>x</script>`'}], 'reviews':[{'reviewer':'independent', 'verdict':'rejected'}], 'invalid_reasons':['dependency invalid']}])
        html = render(snapshot, 'html'); md = render(snapshot, 'markdown')
        self.assertNotIn('<script>', html); self.assertIn('Content-Security-Policy', html)
        for value in ('abc123', 'receipt', 'independent', 'headers', 'limit', '2026-11-01'):
            self.assertIn(value, html); self.assertIn(value, md)
        self.assertNotIn('```<script>', md)
        self.assertIn('过期', html)
        self.assertEqual(json.loads(render(snapshot, 'json')), snapshot)
        with self.assertRaises(ValueError): render(dict(snapshot, secret='hidden'), 'json')
        with self.assertRaises(ValueError): render(snapshot, 'pdf')
    def test_strict_json_types_ids_and_reopen_copies(self):
        Store, Error, parse, validate, _ = self.api()
        store, draft, run = self.run_record(); rid = run['id']
        run['draft']['assets'][0]['name'] = 'mutated'
        self.assertNotEqual(store.get_run(rid)['draft']['assets'][0]['name'], 'mutated')
        for limit in (True, 0, 101):
            with self.assertRaises(Error): store.list_drafts(limit=limit)
        for patch_data in ({'id':rid}, {'plan':[]}, {'policy':{'n':float('inf')}}, {'status':[]}, {'engagement_complete':0}):
            with self.assertRaises(Error): store.update_run(rid, patch_data, expected_revision=1)
        with self.assertRaises(Error): store.create_run(draft['id'], True)
        with self.assertRaises(Error): validate(dict(self.draft(), model_profile_id=uuid.uuid4().hex))
        for target in ('https://a.test/\x1cpath', '123.123', 'https://a.test/%00'):
            self.assertEqual(parse(target)['counts']['valid'], 0)
        assets = self.draft()['assets']; assets[0]['id'] = 'forged'
        self.assertTrue(validate(dict(self.draft(),assets=assets))['assets'][0]['id'].startswith('asset_'))

    def test_narrative_full_unicode_bound_and_conflicts(self):
        _, Error, *_ = self.api()
        store, _, run = self.run_record(); rid = run['id']; fid = uuid.uuid4().hex
        data = {k:'中' * 8000 for k in ('description','impact','reproduction','remediation')}
        self.assertEqual(store.save_narrative(rid,fid,data)['revision'],1)
        with self.assertRaises(Error): store.save_narrative(rid,fid,data,expected_revision=2)
        with self.assertRaises(Error): store.save_narrative(rid,fid,dict(data,severity='high'),expected_revision=1)
        self.assertEqual(store.get_narrative(rid,fid)['data']['impact'],data['impact'])

    def test_messages_cap_and_cross_run_model_association(self):
        Store, Error, *_ = self.api()
        store, draft, run = self.run_record(); rid = run['id']; other = store.create_run(draft['id'],1)['id']
        data = dict(request_id=uuid.uuid4().hex,kind='guidance',text='x')
        message = store.add_message(rid,data)
        pid = str(uuid.uuid4())
        with self.assertRaises(Error): store.reserve_model_call(other,role='Scout',profile_id=pid,purpose='guidance',message_ids=[message['id']])
        call = store.reserve_model_call(rid,role='Scout',profile_id=pid,purpose='guidance',message_ids=[message['id']])
        self.assertEqual(store.messages(rid)[0]['status'],'queued')
        done = store.finish_model_call(rid,call['id'],status='succeeded',result={'ok':True})
        self.assertEqual(store.finish_model_call(rid,call['id'],status='succeeded',result={'ok':True}),done)
        with self.assertRaises(Error): store.finish_model_call(rid,call['id'],status='failed',result={})
        store.finish_message(rid,message['id'],status='consumed',consumer='plan',result='used')
        with self.assertRaises(Error): store.reserve_model_call(rid,role='Scout',profile_id=pid,purpose='guidance',message_ids=[message['id']])
        for _ in range(999): store.add_message(rid,dict(data,request_id=uuid.uuid4().hex))
        self.assertEqual(store.add_message(rid,data)['id'],message['id'])
        with self.assertRaises(Error): store.add_message(rid,dict(data,request_id=uuid.uuid4().hex))
        self.assertEqual(len(Store(self.root).messages(rid)),1000)

    def test_event_bounds_and_global_sequences(self):
        _, Error, *_ = self.api()
        store,draft,run = self.run_record(); rid = run['id']; other = store.create_run(draft['id'],1)['id']
        first = store.append_event(rid,'one',{})
        second = store.append_event(other,'two',{})
        self.assertGreater(second['sequence'],first['sequence'])
        for detail in ({'x':'a'*32768}, {1:'x'}, {'x':float('nan')}):
            with self.assertRaises(Error): store.append_event(rid,'bad',detail)
        for value in (-1,True):
            with self.assertRaises(Error): store.events(rid,after=value)
        with self.assertRaises(Error): store.events(uuid.uuid4().hex)

    def test_csv_limits_newline_fields_and_first_row_wins(self):
        _,Error,parse,_,_ = self.api()
        for value in ('target,name\na.test,"x\ny"','target,group\na.test,"x\ny"'):
            with self.assertRaises(Error): parse(value,'csv')
        result = parse('target,name\na.test,first\na.test,last\n','csv')
        self.assertEqual(result['assets'][0]['name'],'first')
        self.assertEqual(result['counts']['rows'],2)
        with self.assertRaises(Error): parse('target\na.test,extra','csv')

    def test_report_recursive_secret_names_and_all_states(self):
        *_,render = self.api()
        snapshot = dict(version=1,task={},run={},findings=[dict(id=str(i),status=s) for i,s in enumerate(('candidate','confirmed','rejected','inconclusive','stale'))])
        for token in ('候选','已确认','已拒绝','未定论','已过期'): self.assertIn(token,render(snapshot,'html'))
        for secret in ('api_key','Authorization','password','secret'):
            with self.assertRaises(ValueError): render(dict(snapshot,events=[{'detail':{secret:'x'}}]),'markdown')
        self.assertIn('password is prose',render(dict(snapshot,task={'goal':'password is prose'}),'html'))
    def test_scheduler_ids_and_native_coverage_review_report_fields(self):
        _,Error,*_ = self.api()
        store,_,run=self.run_record()
        for action in ('a:b','a.b','a'*129):
            with self.assertRaises(Error): store.add_message(run['id'],dict(request_id=uuid.uuid4().hex,kind='prioritize',text='x',action_ids=[action]))
        *_,render=self.api()
        snapshot=dict(version=1,generated_at='now',task={},run={},coverage={'cells':[{'state':'evidence_gap','reasons':['receipt missing'],'task_id':'task-one','fact_ids':['fact-one']}]},findings=[{'reviews':[{'reviewer':'General','outcome':'confirmed','note':'independent receipt checked','evidence_id':'review-evidence','at':123}]}])
        output=render(snapshot,'html')
        for value in ('receipt missing','task-one','fact-one','independent receipt checked','review-evidence'):
            self.assertIn(value,output)
    def test_unicode_surrogates_and_c1_controls_are_safe_errors(self):
        _,Error,parse,validate,_=self.api()
        for value in ('\ud800','\x85','\x9f'):
            with self.assertRaises(Error): validate(dict(self.draft(),context=value))
        with self.assertRaises(Error): parse('\ud800')
        store,_,run=self.run_record()
        for value in ('\ud800','\x85'):
            with self.assertRaises(Error): store.add_message(run['id'],dict(request_id=uuid.uuid4().hex,kind='guidance',text=value))
    def test_import_text_keyword_contract(self):
        _,_,parse,_,_=self.api()
        self.assertEqual(parse(text='example.test')['counts']['valid'],1)

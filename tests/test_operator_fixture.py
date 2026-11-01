"""Browser fixture contract through the real authenticated operator HTTP API."""
import http.client
import json
import socket
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).parent / 'browser'))
from operator_workspace_fixture import OperatorFixture, SYNTHETIC_KEY
from operator_fixture_relay import RelayServer


class OperatorFixtureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.fixture = OperatorFixture(Path(self.tmp.name), port=0).start()
        self.addCleanup(lambda: self.fixture.close())
        self.login()

    def request(self, method, path, body=None, expected=200):
        headers = {'Origin': self.fixture.origin, 'Content-Type': 'application/json'}
        if getattr(self, 'cookie', None):
            headers.update(Cookie=self.cookie, **{'X-Sapper-CSRF': self.csrf})
        conn = http.client.HTTPConnection('127.0.0.1', self.fixture.port, timeout=10)
        try:
            conn.request(method, path, json.dumps(body).encode() if body is not None else None, headers)
            response = conn.getresponse(); raw = response.read()
            self.assertEqual(response.status, expected, raw)
            return json.loads(raw), dict(response.getheaders())
        finally:
            conn.close()

    def api(self, method, path, body=None, expected=200):
        return self.request(method, path, body, expected)[0]

    def login(self):
        self.cookie = None
        data, headers = self.request('POST', '/api/session', {'token': self.fixture.http.bootstrap_token})
        self.cookie = headers['Set-Cookie'].split(';')[0]; self.csrf = data['csrf_token']

    def settle(self, rid):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            snap = self.api('GET', '/api/runs/' + rid)['snapshot']
            if (snap['run']['status'] not in ('preparing', 'running', 'pause_requested', 'cancel_requested')
                and not any(m['status']=='queued' for m in snap['messages'])
                and not any(c['status']=='reserved' for c in snap['model_calls'])):
                return snap
            time.sleep(.03)
        self.fail('fixture job did not settle')

    def prepare(self, paths=('/alpha', '/beta')):
        profile = self.api('POST', '/api/models', {'profile': self.fixture.profile()})['profile']
        assets = self.api('POST', '/api/assets/preview', dict(text='\n'.join(self.fixture.target_origin+p for p in paths), format='lines'))['preview']['assets']
        draft = self.api('POST', '/api/tasks', {'data': dict(name='Synthetic browser task', goal='Observe fixtures only',
            assets=assets, model_profile_id=profile['id'], allowed_tools=['http_get', 'http_head'],
            max_request_seconds=30, max_response_bytes=8192, budgets=dict(seconds=600, model_calls=40))})['task']
        rid = self.api('POST', '/api/tasks/'+draft['id']+'/runs', {'expected_revision': draft['revision']}, 202)['run']['id']
        return self.settle(rid)

    def execute(self, snap):
        rid = snap['run']['id']; prefix = '/api/runs/'+rid
        self.api('POST', prefix+'/approve', dict(plan_revision=snap['plan']['revision'],
            action_ids=[a['id'] for a in snap['plan']['actions'] if a['state']=='pending'], actor='fixture operator'))
        self.api('POST', prefix+'/start', {})
        return self.settle(rid)

    def message(self, rid, kind, text, **kw):
        return self.api('POST', '/api/runs/'+rid+'/messages', dict(request_id=uuid.uuid4().hex, kind=kind, text=text, **kw))

    def test_real_plan_guidance_candidate_and_independent_advisory_retest(self):
        self.assertEqual(self.fixture.readiness()['counts']['target_total'], 0)
        snap = self.prepare(); rid = snap['run']['id']
        self.assertEqual(snap['run']['status'], 'awaiting_approval')
        self.assertEqual({a['role'] for a in snap['plan']['actions']}, {'Scout','Soldier'})
        self.assertEqual(self.fixture.metadata()['counts']['target_total'], 0)
        snap = self.execute(snap)
        self.assertEqual(snap['run']['status'], 'completed')
        self.assertEqual(len(snap['findings']), 1)
        case = snap['findings'][0]; self.assertEqual(case['status'], 'candidate')
        self.assertTrue(all(t['receipt_state']=='verified' for t in snap['runtime']['tasks']))
        self.assertIn('<script>', case['evidence'][0]['excerpt'])
        self.message(rid, 'guidance', 'Please observe /guided only')
        snap = self.settle(rid)
        self.assertEqual(self.fixture.metadata()['counts']['target_total'], 2)
        pending = [a for a in snap['plan']['actions'] if a['state']=='pending']
        self.assertEqual([a['target'] for a in pending], [self.fixture.target_origin+'/guided'])
        self.message(rid, 'guidance', 'Do not duplicate the pending /guided observation')
        snap = self.settle(rid)
        self.assertEqual(len([a for a in snap['plan']['actions'] if a['state']=='pending']), 1)
        snap = self.execute(snap)
        self.message(rid, 'guidance', 'Keep prior guidance in context')
        snap = self.settle(rid)
        contexts = self.fixture.records()['model_calls']
        self.assertTrue(any(c['context'] and c['context']['history'] for c in contexts))
        self.message(rid, 'retest', 'Independent exact alpha retest', finding_id=case['id'])
        snap = self.settle(rid)
        self.assertEqual(self.fixture.metadata()['counts']['target_total'], 3)
        snap = self.execute(snap)
        self.assertEqual(self.fixture.metadata()['counts']['target_total'], 4)
        self.assertEqual(snap['findings'][0]['status'], 'candidate')
        self.assertEqual(snap['review_suggestions'][0]['state'], 'suggested')
        self.assertTrue(snap['review_suggestions'][0]['evidence_current_valid'])
        review_context=next(c['context'] for c in self.fixture.records()['model_calls'] if c['purpose']=='review')
        self.assertEqual(review_context['role'],'General')
        original=case['evidence'][0]
        fresh=next(e for o in snap['observations'] for e in o['evidence'] if e['id']==snap['review_suggestions'][0]['evidence_id'])
        self.assertEqual(fresh['target'],original['target'])
        self.assertNotEqual(fresh['receipt_id'],original['receipt_id'])
        self.assertGreaterEqual(fresh['started_at'],original['finished_at'])
        emitted=self.fixture.records()['emitted_fact_ids']
        self.assertEqual(emitted.count(case['fact_id']), 1)
        self.assertEqual(len(emitted), len(set(emitted)))
        self.assertNotIn(SYNTHETIC_KEY, json.dumps(contexts))

    def test_barrier_failure_and_restart_keep_counts_without_replay(self):
        self.fixture.control('arm')
        snap = self.prepare(('/slow',)); rid = snap['run']['id']; prefix='/api/runs/'+rid
        self.api('POST', prefix+'/approve', dict(plan_revision=snap['plan']['revision'], action_ids=[snap['plan']['actions'][0]['id']], actor='fixture'))
        self.api('POST', prefix+'/start', {})
        deadline=time.monotonic()+5
        while not self.fixture.metadata()['barrier']['pending'] and time.monotonic()<deadline: time.sleep(.02)
        self.assertTrue(self.fixture.metadata()['barrier']['pending'])
        self.assertEqual(self.api('POST', prefix+'/pause', {})['run']['status'], 'pause_requested')
        self.fixture.control('release'); self.assertEqual(self.settle(rid)['run']['status'], 'paused')
        self.fixture.control('fail_next', 'plan')
        failed = self.prepare(('/beta',))
        self.assertEqual(failed['run']['status'], 'blocked')
        before=self.fixture.metadata()['counts']; old_token=self.fixture.http.bootstrap_token
        home=self.fixture.home; port=self.fixture.port
        self.fixture.close(); self.fixture=OperatorFixture(home, port=port).start(); self.login()
        self.assertNotEqual(old_token, self.fixture.http.bootstrap_token)
        self.assertEqual(self.fixture.readiness()['counts'], before)
        self.assertEqual(self.api('GET', prefix)['snapshot']['run']['status'], 'paused')
        self.assertEqual(self.fixture.metadata()['generation'], 2)
        self.assertEqual(self.fixture.metadata()['counts'], before)

    def test_probe_bad_profile_head_failure_and_rejected_key_are_bounded(self):
        good=self.api('POST', '/api/models', {'profile':self.fixture.profile()})['profile']
        self.api('POST', '/api/models/'+good['id']+'/test', {})
        self.assertEqual(self.fixture.metadata()['counts']['model_by_purpose']['probe'], 1)
        bad=self.api('POST', '/api/models', {'profile':self.fixture.profile(bad=True)})['profile']
        error=self.api('POST', '/api/models/'+bad['id']+'/test', {}, expected=503)
        self.assertNotIn(SYNTHETIC_KEY,json.dumps(error))
        conn=http.client.HTTPConnection('127.0.0.1',9551,timeout=5)
        try:
            conn.request('HEAD','/alpha'); response=conn.getresponse(); self.assertEqual(response.status,200); response.read()
            conn.request('GET','/failure'); response=conn.getresponse(); self.assertEqual(response.status,503); response.read()
        finally: conn.close()
        conn=http.client.HTTPConnection('127.0.0.1',9552,timeout=5)
        try:
            conn.request('POST','/good/chat/completions',b'{}',{'Authorization':'Bearer arbitrary-unrecorded-key','Content-Length':'2'})
            response=conn.getresponse(); self.assertEqual(response.status,401); response.read()
        finally: conn.close()
        records=self.fixture.records()
        self.assertEqual([h['method'] for h in records['target_hits']],['HEAD','GET'])
        self.assertEqual([h['status'] for h in records['target_hits']],[200,503])
        self.assertEqual(len(records['model_calls']),2)
        self.assertNotIn('arbitrary-unrecorded-key',json.dumps(records))

    def test_relay_preserves_real_auth_origin_csrf_and_exact_peer(self):
        relay=RelayServer(('127.0.0.1',0),'127.0.0.1',self.fixture.port)
        thread=threading.Thread(target=relay.serve_forever,kwargs={'poll_interval':.05}); thread.start()
        try:
            conn=http.client.HTTPConnection('127.0.0.1',relay.server_address[1],timeout=5)
            try:
                conn.request('GET','/api/tasks',headers={'Host':self.fixture.origin.removeprefix('http://'),'Cookie':self.cookie})
                response=conn.getresponse(); self.assertEqual(response.status,200); response.read()
                conn.request('POST','/api/assets/preview',json.dumps(dict(text=self.fixture.target_origin+'/alpha',format='lines')),
                    {'Host':self.fixture.origin.removeprefix('http://'),'Origin':self.fixture.origin,'Cookie':self.cookie,
                     'X-Sapper-CSRF':self.csrf,'Content-Type':'application/json'})
                response=conn.getresponse(); self.assertEqual(response.status,200); response.read()
            finally: conn.close()
            self.assertEqual(self.fixture.metadata()['counts']['target_total'],0)
            self.assertEqual(self.fixture.metadata()['counts']['model_total'],0)
        finally:
            relay.shutdown(); relay.close_connections(); relay.server_close(); thread.join(5)
            self.assertFalse(thread.is_alive())

    def test_relay_rejects_dns_peer_and_ninth_connection_and_joins_clients(self):
        with self.assertRaises(ValueError): RelayServer(('127.0.0.1',0),'example.invalid',self.fixture.port)
        with self.assertRaises(ValueError): RelayServer(('127.0.0.1',0),'127.0.0.1',8765)
        relay=RelayServer(('127.0.0.1',0),'127.0.0.1',self.fixture.port)
        thread=threading.Thread(target=relay.serve_forever,kwargs={'poll_interval':.05}); thread.start()
        clients=[]
        try:
            for _ in range(8): clients.append(socket.create_connection(relay.server_address,timeout=3))
            deadline=time.monotonic()+3
            while len(relay.sockets)<8 and time.monotonic()<deadline: time.sleep(.01)
            self.assertEqual(len(relay.sockets),8)
            ninth=socket.create_connection(relay.server_address,timeout=3)
            try: self.assertEqual(ninth.recv(1),b'')
            finally: ninth.close()
        finally:
            for client in clients: client.close()
            relay.shutdown(); relay.close_connections(); relay.server_close(); thread.join(5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(self.fixture.metadata()['counts']['target_total'],0)

    def test_close_releases_pending_slow_request_and_joins_owned_threads(self):
        self.fixture.control('arm')
        snap=self.prepare(('/slow',)); rid=snap['run']['id']; prefix='/api/runs/'+rid
        self.api('POST',prefix+'/approve',dict(plan_revision=snap['plan']['revision'],action_ids=[snap['plan']['actions'][0]['id']],actor='fixture'))
        self.api('POST',prefix+'/start',{})
        deadline=time.monotonic()+5
        while not self.fixture.metadata()['barrier']['pending'] and time.monotonic()<deadline: time.sleep(.02)
        self.assertTrue(self.fixture.metadata()['barrier']['pending'])
        threads=list(self.fixture.threads)
        started=time.monotonic(); self.fixture.close()
        self.assertLess(time.monotonic()-started,5)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertFalse((self.fixture.state/'bootstrap.url').exists())
        self.assertEqual(self.fixture.records()['target_hits'][0]['path'],'/slow')


if __name__ == '__main__': unittest.main()

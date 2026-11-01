"""Real loopback HTTP boundary over the protected Workspace and model transport."""
import contextlib
import http.client
import http.server
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import unittest
import uuid
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import test_workspace_runtime as runtime
try:
    from pentest.workspace_http import create_server, MAX_BODY, MAX_WORKERS
except ImportError:
    create_server = None


class HTTPTests(unittest.TestCase):
    cleanup_server = runtime.WorkspaceTests.cleanup_server

    def setUp(self):
        self.assertIsNotNone(create_server, 'authenticated typed HTTP bridge is missing')
        runtime.WorkspaceTests.setUp(self)
        self.http = None
        self.cookie = self.csrf = None
        self.logs = io.StringIO()
        self.addCleanup(self.stop_http)

    def start_http(self, **kw):
        self.http = create_server(workspace=self.ws, **kw)
        self.http_thread = threading.Thread(target=self.http.serve_forever)
        self.http_thread.start()
        self.host = '127.0.0.1:' + str(self.http.server_port)
        self.url = 'http://' + self.host

    def stop_http(self):
        if self.http:
            self.http.close(); self.http_thread.join(3)
            self.assertFalse(self.http_thread.is_alive())
            self.http = None

    def request(self, method, path, body=None, *, auth=True, headers=None, raw=None):
        h = {}
        if method == 'POST': h.update(Origin=self.url, **{'Content-Type':'application/json'})
        if auth and self.cookie:
            h['Cookie'] = self.cookie
            if method == 'POST': h['X-Sapper-CSRF'] = self.csrf
        h.update(headers or {})
        payload = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        conn = http.client.HTTPConnection('127.0.0.1', self.http.server_port, timeout=8)
        with contextlib.redirect_stderr(self.logs):
            conn.request(method, path, body=payload, headers=h)
            response = conn.getresponse(); data = response.read(); meta = dict(response.getheaders())
        conn.close()
        value = json.loads(data) if data and meta.get('Content-Type','').startswith('application/json') else data
        return response.status, value, meta

    def session(self):
        status, value, headers = self.request('POST','/api/session',dict(token=self.http.bootstrap_token),auth=False)
        self.assertEqual(status,200,value)
        self.cookie = headers['Set-Cookie'].split(';')[0]; self.csrf = value['csrf_token']
        self.assertIn('HttpOnly',headers['Set-Cookie']); self.assertIn('SameSite=Strict',headers['Set-Cookie'])
        self.assertIn(str(self.http.server_port),self.cookie)

    def ok(self, method, path, body=None, status=200):
        actual, value, _ = self.request(method,path,body)
        self.assertEqual(actual,status,value)
        return value

    def draft(self, **changes):
        assets=self.ok('POST','/api/assets/preview',dict(text=self.origin+'/',format='lines'))['preview']['assets']
        data=dict(name='Fixture <script>alert(1)</script>',goal='Observe exact fixture',assets=assets,
                  allowed_tools=['http_get'],max_request_seconds=4,max_response_bytes=1024)
        data.update(changes)
        return self.ok('POST','/api/tasks',dict(data=data))['task']

    def prepare(self, **changes):
        draft=self.draft(**changes)
        rid=self.ok('POST','/api/tasks/'+draft['id']+'/runs',dict(expected_revision=1),202)['run']['id']
        self.ws.wait(rid,10)
        return self.snap(rid)

    def snap(self,rid): return self.ok('GET','/api/runs/'+rid)['snapshot']

    def model_fixture(self):
        from pentest.models import ModelProfiles
        from pentest.workspace import Workspace
        self.model_requests=[]; self.model_mode='ok'; owner=self
        class ModelHandler(http.server.BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(self):
                payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                self_context=payload['messages'][-1]['content']
                context=json.loads(self_context) if self_context!='Reply OK.' else None
                owner.model_requests.append((payload,context))
                if owner.model_mode=='error' or (owner.model_mode=='analysis_error' and context and context['purpose']=='analyze'):
                    self.send_response(429); self.end_headers(); return
                if context is None: proposal='OK'
                elif context['purpose']=='plan':
                    asset=context['draft']['assets'][0]
                    target=owner.origin+'/new' if context['guidance'] else asset['target']
                    proposal=json.dumps(dict(summary='Fixture plan',gaps=['Manual checks remain'],actions=[dict(
                        asset_id=asset['id'],target=target,tool='http_get',role='Scout',description='Fixture',risk=2,evidence_gap=1)]))
                else: proposal=json.dumps(dict(summary='Observed fixture',gaps=[],findings=[]))
                raw=json.dumps(dict(choices=[dict(message=dict(content=proposal))],model=payload['model'],usage=dict(prompt_tokens=1,completion_tokens=1,total_tokens=2))).encode()
                self.send_response(200); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),ModelHandler)
        worker=threading.Thread(target=server.serve_forever); worker.start()
        def cleanup(): server.shutdown(); server.server_close(); worker.join(3)
        self.addCleanup(cleanup)
        self.ws.close()
        profiles=ModelProfiles(Path(self.tmp.name)/'profiles',allow_http_loopback=True)
        def profile(name):
            return profiles.save(dict(name=name,provider='custom',base_url='http://127.0.0.1:%s/v1'%server.server_port,
                                      model=name,api_key='synthetic-key',timeout_seconds=5))
        self.default_profile=profile('commander'); self.scout_profile=profile('scout'); self.general_profile=profile('general')
        self.ws=Workspace(self.root,models=profiles); self.addCleanup(self.ws.close)
        return dict(model_profile_id=self.default_profile['id'],role_profiles=dict(Scout=self.scout_profile['id'],General=self.general_profile['id']))

    def execute(self,snap):
        rid=snap['run']['id']; prefix='/api/runs/'+rid
        self.ok('POST',prefix+'/approve',dict(plan_revision=snap['plan']['revision'],
                    action_ids=[a['id'] for a in snap['plan']['actions'] if a['state']=='pending'],actor='operator'))
        self.ok('POST',prefix+'/start',{})
        self.ws.wait(rid,10)
        return self.snap(rid)

    def test_bootstrap_reload_csrf_and_restart(self):
        self.start_http()
        self.assertEqual(self.request('GET','/api/tasks')[0],403)
        self.assertEqual(self.request('POST','/api/session',dict(token='wrong'),auth=False)[0],403)
        self.session()
        self.assertEqual(self.ok('GET','/api/session')['csrf_token'],self.csrf)
        for headers in ({'X-Sapper-CSRF':'bad'}, {'Origin':'http://evil.invalid'}, {'Origin':''}):
            self.assertEqual(self.request('POST','/api/tasks',dict(data={}),headers=headers)[0],403)
        old_cookie=self.cookie; old_token=self.http.bootstrap_token
        self.stop_http(); self.start_http()
        self.assertEqual(self.request('GET','/api/tasks',headers={'Cookie':old_cookie})[0],403)
        self.assertEqual(self.request('POST','/api/session',dict(token=old_token),auth=False)[0],403)
        self.assertEqual(self.logs.getvalue(),'')

    def test_host_origin_duplicates_framing_and_method_override(self):
        self.start_http(); self.session()
        cases=[('Host',self.host),('Origin',self.url),('Cookie',self.cookie),
               ('X-Sapper-CSRF',self.csrf),('Authorization','one'),('Content-Length','2')]
        for key,value in cases:
            with self.subTest(header=key):
                conn=http.client.HTTPConnection('127.0.0.1',self.http.server_port,timeout=3)
                conn.putrequest('POST','/api/tasks',skip_host=True)
                hs=[('Host',self.host),('Origin',self.url),('Cookie',self.cookie),('X-Sapper-CSRF',self.csrf),
                    ('Content-Type','application/json'),('Content-Length','2')]
                if key=='Authorization': hs.append((key,value))
                for k,v in hs+[(key,value)]: conn.putheader(k,v)
                conn.endheaders(b'{}'); res=conn.getresponse()
                self.assertIn(res.status,(400,403)); res.read(); conn.close()
        for headers in ({'Host':'localhost:'+str(self.http.server_port)}, {'Transfer-Encoding':'chunked'},
                        {'X-HTTP-Method-Override':'GET'},{'Content-Type':'text/plain'}):
            self.assertIn(self.request('POST','/api/tasks',{},headers=headers)[0],(400,403,415))
        self.assertEqual(self.hits,[])

    def test_strict_json_queries_paths_methods_and_bounds(self):
        self.start_http(); self.session()
        for raw in (b'{"text":"x","text":"y","format":"lines"}',b'{"text":NaN}',b'[]',
                    b'{"text":"\\ud800","format":"lines"}',b'{"text":"\xff"}',b'{"x":'+b'1'*5000+b'}'):
            self.assertEqual(self.request('POST','/api/assets/preview',raw=raw)[0],400)
        for path in ('/api/tasks?limit=1&limit=2','/api/tasks?wat=1','/api/tasks?limit=true',
                     '/api/tasks?offset=-1','/api/tasks?limit=101','/api/tasks?limit=%31','/api/tasks?limit=01'):
            self.assertEqual(self.request('GET',path)[0],400,path)
        for path in ('//api/tasks','/api/%74asks','/../api/tasks','/api/tasks/','/api/tasks/'+str(uuid.uuid4()),
                     '/app.js?file=x','/operator_web/../workspace.py','http://'+self.host+'/api/tasks'):
            self.assertIn(self.request('GET',path)[0],(400,404),path)
        for method in ('HEAD','PUT','DELETE','OPTIONS','PATCH','TRACE','CONNECT'):
            self.assertEqual(self.request(method,'/api/tasks')[0],405,method)
        # Length is rejected before reading a body; do not race sendall against close.
        status, value, _ = self.request('POST','/api/assets/preview',raw=b'',
                                      headers={'Content-Length':str(MAX_BODY+1)})
        self.assertEqual(status,413)
        self.assertEqual(value,{'error':{'code':'payload_too_large','message':'请求超过一兆字节限制'}})
        self.assertEqual(self.hits,[])

    def test_static_allowlist_headers_and_safe_errors(self):
        self.start_http()
        status,body,headers=self.request('GET','/')
        self.assertEqual(status,200)
        from pentest import workspace_http as adapter
        if not (adapter.WEB/'index.html').is_file(): self.assertIn(b'backend',body.lower())
        self.assertIn("frame-src 'self'",headers['Content-Security-Policy'])
        self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertEqual(headers['Referrer-Policy'],'no-referrer')
        self.assertEqual(headers['X-Content-Type-Options'],'nosniff')
        for path in ('/app.js','/api.js','/task_editor.js','/run_view.js','/models_view.js','/findings_view.js','/ui.js','/coverage_view.js','/report_view.js','/app.css'):
            self.assertEqual(self.request('GET',path)[0],200 if (adapter.WEB/path[1:]).is_file() else 404)
        self.session()
        status,error,_=self.request('POST','/api/models',dict(profile=dict(api_key='synthetic-key'),unknown='synthetic-key'))
        self.assertEqual(status,400); self.assertEqual(set(error),{'error'})
        self.assertEqual(set(error['error']),{'code','message'})
        self.assertNotIn('synthetic-key',json.dumps(error)+self.logs.getvalue())
        self.assertTrue(any(ord(c)>127 for c in error['error']['message']))
        fixtures=Path(self.tmp.name)/'static'; fixtures.mkdir()
        for route,(name,mime) in adapter.STATIC.items(): (fixtures/name).write_bytes(('packaged '+name).encode())
        (fixtures/'private.txt').write_text('synthetic-key')
        with mock.patch.object(adapter,'WEB',fixtures):
            for route,(name,mime) in adapter.STATIC.items():
                code,data,h=self.request('GET',route)
                self.assertEqual(code,200); self.assertEqual(data,('packaged '+name).encode())
                self.assertEqual(h['Content-Type'],mime+'; charset=utf-8')
            self.assertEqual(self.request('GET','/private.txt')[0],404)

    def test_draft_preview_revision_pagination_gets_are_inert(self):
        self.start_http(); self.session()
        preview=self.ok('POST','/api/assets/preview',dict(text=self.origin+'/\n'+self.origin+'/\nbad/path',format='lines'))['preview']
        self.assertEqual(preview['counts']['duplicates'],1); self.assertEqual(preview['counts']['invalid'],1)
        task=self.draft(); tid=task['id']
        self.assertEqual(self.ok('GET','/api/tasks?limit=1&offset=0')['tasks'][0]['id'],tid)
        self.assertEqual(self.ok('GET','/api/tasks/'+tid),dict(task=task,runs=[]))
        task['data']['goal']='Updated'
        self.assertEqual(self.ok('POST','/api/tasks/'+tid,dict(data=task['data'],expected_revision=1))['task']['revision'],2)
        self.assertEqual(self.request('POST','/api/tasks/'+tid,dict(data=task['data'],expected_revision=1))[0],409)
        for data in ({'data':task['data'],'expected_revision':True},{'data':task['data'],'extra':1}):
            self.assertEqual(self.request('POST','/api/tasks/'+tid,data)[0],400)
        first=self.ws.store.create_run(tid,2); second=self.ws.store.create_run(tid,2)
        page0=self.ok('GET','/api/tasks/'+tid+'/runs?limit=1&offset=0')['runs']
        page1=self.ok('GET','/api/tasks/'+tid+'/runs?limit=1&offset=1')['runs']
        self.assertEqual({page0[0]['id'],page1[0]['id']},{first['id'],second['id']})
        for query in ('limit=1&limit=2','limit=101','offset=-1','unknown=1'):
            self.assertEqual(self.request('GET','/api/tasks/'+tid+'/runs?'+query)[0],400)
        self.assertEqual(self.request('GET','/api/tasks/'+'f'*32+'/runs')[0],404)
        self.assertEqual(self.hits,[]); self.assertFalse((self.root/'runs').exists())

    def test_real_prepare_approve_execute_messages_coverage_findings_and_reports(self):
        self.start_http(); self.session(); snap=self.prepare(); rid=snap['run']['id']; p='/api/runs/'+rid
        self.assertEqual(self.hits,[])
        self.assertEqual(self.request('GET',p+'/start')[0],405)
        self.assertEqual(self.request('POST',p+'/approve',dict(plan_revision=99,action_ids=[snap['plan']['actions'][0]['id']],actor='operator'))[0],409)
        snap=self.execute(snap); self.assertEqual(len(self.hits),1)
        msg=dict(request_id=uuid.uuid4().hex,kind='guidance',text='Record this explicitly')
        self.assertEqual(self.ok('POST',p+'/messages',msg)['message']['consumer'],'operator-record')
        fact=snap['runtime']['evidence']['facts'][0]
        manual=next(c for c in snap['coverage']['checks'] if c['method']=='manual')
        asset=snap['coverage']['assets'][0]
        self.ok('POST',p+'/coverage/assess',dict(asset_id=asset['id'],check_id=manual['id'],outcome='completed',
                         actor='operator',note='Checked fixture',fact_ids=[fact['id']]))
        data=dict(fact_id=fact['id'],title='Candidate',severity='low',reporter='operator',description='Description <script>bad</script>',
                  impact='Impact',reproduction='GET fixture',remediation='Review',cwe='',operator_note='')
        case=self.ok('POST',p+'/findings',data)['finding']; f=p+'/findings/'+case['id']
        self.assertEqual(self.ok('GET',f)['finding'],case)
        narrative={k:data[k] for k in ('description','impact','reproduction','remediation','cwe','operator_note')}
        narrative['impact']='Updated impact'
        case=self.ok('POST',f+'/narrative',dict(data=narrative,expected_revision=1))['finding']
        self.assertEqual(case['narrative_revision'],2)
        self.assertEqual(self.request('POST',f+'/narrative',dict(data=narrative,expected_revision=1))[0],409)
        self.ok('POST',p+'/messages',dict(request_id=uuid.uuid4().hex,kind='retest',text='Independent retest',finding_id=case['id']))
        snap=self.execute(self.snap(rid)); original=case['evidence'][0]['id']
        evidence=next(e for e in snap['runtime']['evidence']['evidence'] if e['id']!=original)
        case=self.ok('POST',f+'/review',dict(reviewer='independent',evidence_id=evidence['id'],outcome='confirmed',note='Reviewed'))['finding']
        self.assertEqual(case['status'],'confirmed')
        self.ok('POST',p+'/facts/'+fact['id']+'/invalidate',dict(actor='operator',reason='Withdraw claim'))
        self.assertEqual(self.ok('GET',f)['finding']['status'],'stale')
        for fmt in ('html','markdown','json'):
            status,report,h=self.request('GET',p+'/report?format='+fmt)
            self.assertEqual(status,200); self.assertIn('attachment',h['Content-Disposition'])
            self.assertNotIn('synthetic-secret',str(report)); self.assertNotIn('synthetic-key',str(report))
        _,report,h=self.request('GET',p+'/report?format=html&download=0')
        self.assertIn('inline',h['Content-Disposition']); self.assertIn("frame-ancestors 'self'",h['Content-Security-Policy'])
        self.assertNotIn('style-src',h['Content-Security-Policy']); self.assertIn(b'default-src &apos;none&apos;',report)
        self.assertNotIn(b'<script>bad</script>',report)
        for query in ('format=json&download=0','format=html&download=true','format=html&download=0&download=1'):
            self.assertEqual(self.request('GET',p+'/report?'+query)[0],400)
        self.assertEqual(len(self.hits),2)

    def test_pause_resume_cancel_typed_routes_preserve_completed_requests(self):
        self.start_http(); self.session()
        assets=self.ok('POST','/api/assets/preview',dict(text=self.origin+'/wait\n'+self.origin+'/two',format='lines'))['preview']['assets']
        def begin():
            snap=self.prepare(assets=assets); rid=snap['run']['id']; p='/api/runs/'+rid
            first=next(a for a in snap['plan']['actions'] if a['target'].endswith('/wait'))
            self.ok('POST',p+'/messages',dict(request_id=uuid.uuid4().hex,kind='prioritize',text='Wait first',action_ids=[first['id']]))
            self.ok('POST',p+'/approve',dict(plan_revision=snap['plan']['revision'],action_ids=[a['id'] for a in snap['plan']['actions']],actor='operator'))
            self.ok('POST',p+'/start',{}); self.assertTrue(self.entered.wait(3))
            return rid,p
        rid,p=begin()
        self.assertEqual(self.ok('POST',p+'/pause',{})['run']['status'],'pause_requested')
        self.release.set(); self.ws.wait(rid,10)
        self.assertEqual(self.snap(rid)['run']['status'],'paused'); self.assertEqual(len(self.hits),1)
        self.ok('POST',p+'/resume',{}); self.ws.wait(rid,10)
        self.assertEqual(self.snap(rid)['run']['status'],'completed'); self.assertEqual(len(self.hits),2)
        self.entered.clear(); self.release.clear()
        rid,p=begin()
        self.assertEqual(self.ok('POST',p+'/cancel',{})['run']['status'],'cancel_requested')
        self.release.set(); self.ws.wait(rid,10)
        self.assertEqual(self.snap(rid)['run']['status'],'cancelled')
        self.assertEqual(self.request('POST',p+'/resume',{})[0],409); self.assertEqual(len(self.hits),3)

    def test_profiles_test_safe_failure_endpoint_binding_and_model_resume(self):
        config=self.model_fixture()
        self.start_http(); self.session()
        profiles=self.ok('GET','/api/models')
        self.assertEqual(len(profiles['profiles']),3); self.assertIn('deepseek',profiles['presets'])
        profile=self.default_profile
        self.assertEqual(self.ok('GET','/api/models/'+profile['id'])['profile'],profile)
        data={k:profile[k] for k in ('name','provider','base_url','model','timeout_seconds','max_output_tokens')}
        changed=dict(data,base_url='http://127.0.0.1:1/other')
        self.assertEqual(self.request('POST','/api/models',dict(profile=changed,profile_id=profile['id']))[0],422)
        updated=self.ok('POST','/api/models',dict(profile=dict(data,name='Updated'),profile_id=profile['id']))['profile']
        self.assertEqual(updated['revision'],2); self.assertEqual(self.model_requests,[])
        new=self.ok('POST','/api/models',dict(profile=dict(data,name='HTTP new',api_key='synthetic-key')))['profile']
        self.assertTrue(new['has_key']); self.assertNotIn('synthetic-key',json.dumps(new))
        self.assertEqual(self.model_requests,[])
        self.assertEqual(self.request('POST','/api/models',dict(profile=dict(data,api_key='synthetic-key',unknown='synthetic-key')))[0],400)
        # The actual transport fixture distinguishes minimal connection tests from planning.
        self.assertEqual(self.ok('POST','/api/models/'+profile['id']+'/test',{})['test']['status'],'ok')
        self.model_mode='error'
        status,error,_=self.request('POST','/api/models/'+profile['id']+'/test',{})
        self.assertEqual(status,503); self.assertNotIn('synthetic-key',str(error)+self.logs.getvalue())
        self.model_mode='analysis_error'
        snap=self.prepare(**config); rid=snap['run']['id']; snap=self.execute(snap)
        self.assertEqual(snap['run']['status'],'blocked'); self.assertEqual(len(self.hits),1)
        self.model_mode='ok'
        self.ok('POST','/api/models',dict(profile=data,profile_id=self.scout_profile['id']))
        self.ok('POST','/api/runs/'+rid+'/resume',{}); self.ws.wait(rid,10)
        self.assertEqual(self.snap(rid)['run']['status'],'completed'); self.assertEqual(len(self.hits),1)
        msg=self.ok('POST','/api/runs/'+rid+'/messages',dict(request_id=uuid.uuid4().hex,kind='guidance',text='Look at /new'))['message']
        self.ws.wait(rid,10)
        actual=next(m for m in self.snap(rid)['messages'] if m['id']==msg['id'])
        self.assertEqual(actual['status'],'consumed'); self.assertNotEqual(actual['consumer'],'operator-record')
        self.assertEqual(len(self.hits),1)
        self.ok('POST','/api/models/'+self.general_profile['id']+'/delete',{})
        self.assertEqual(len(self.ok('GET','/api/models')['profiles']),3)

    def test_worker_bound_receive_deadline_and_explicit_ownership(self):
        self.start_http(); self.session()
        self.assertEqual(MAX_WORKERS,8)
        sockets=[]
        try:
            for _ in range(MAX_WORKERS):
                sock=socket.create_connection(('127.0.0.1',self.http.server_port),timeout=3)
                sock.sendall(b'GET / HTTP/1.1\r\nHost: '); sockets.append(sock)
            time.sleep(.1)
            self.assertEqual(self.request('GET','/')[0],503)
        finally:
            for sock in sockets: sock.close()
        time.sleep(.1)
        self.stop_http()
        self.assertFalse(self.ws._closed)
        self.start_http(owns_workspace=True); self.stop_http()
        self.assertTrue(self.ws._closed)

    def test_absolute_deadline_closes_trickled_headers_and_body_without_writes(self):
        self.start_http(); self.session()
        sockets=[]
        for _ in range(2): sockets.append(socket.create_connection(('127.0.0.1',self.http.server_port),timeout=2))
        sockets[0].sendall(b'GET /api/tasks HTTP/1.1\r\nX-Trickle: ')
        header=('POST /api/tasks HTTP/1.1\r\nHost: '+self.host+'\r\nOrigin: '+self.url+
                '\r\nCookie: '+self.cookie+'\r\nX-Sapper-CSRF: '+self.csrf+
                '\r\nContent-Type: application/json\r\nContent-Length: 1000\r\n\r\n')
        sockets[1].sendall(header.encode())
        started=time.monotonic(); disconnected=set()
        try:
            while time.monotonic()-started<12 and len(disconnected)<2:
                for i,sock in enumerate(sockets):
                    if i in disconnected: continue
                    try: sock.sendall(b' ')
                    except OSError: disconnected.add(i)
                time.sleep(.15)
            for i,sock in enumerate(sockets):
                if i not in disconnected:
                    sock.settimeout(.2)
                    try:
                        if not sock.recv(4096): disconnected.add(i)
                    except ConnectionResetError: disconnected.add(i)
            self.assertEqual(disconnected,{0,1})
            self.assertLess(time.monotonic()-started,12.5)
        finally:
            for sock in sockets: sock.close()
        self.assertEqual(self.ws.store.list_drafts(),[]); self.assertEqual(self.hits,[])
        self.assertEqual(self.logs.getvalue(),'')

    def test_framework_errors_and_unexpected_exceptions_never_echo_or_log(self):
        self.start_http(); self.session()
        with contextlib.redirect_stderr(self.logs):
            for request in (b'BAD_SYNTHETIC_KEY /synthetic-key HTTP/1.1\r\n\r\n',
                            b'GET /synthetic-key HTTP/9.9\r\n\r\n',
                            b'GET / HTTP/1.1\r\n'+b'X-Large: '+b'synthetic-key'*6000+b'\r\n\r\n'):
                with socket.create_connection(('127.0.0.1',self.http.server_port),timeout=3) as sock:
                    sock.sendall(request); result=sock.recv(8192)
                    self.assertNotIn(b'synthetic-key',result.lower())
                    self.assertNotIn(b'BAD_SYNTHETIC_KEY',result)
            with mock.patch.object(self.ws.models,'list',side_effect=RuntimeError('synthetic-key https://private.invalid')):
                status,result,_=self.request('GET','/api/models')
                self.assertEqual(status,503); self.assertNotIn('synthetic-key',str(result))
        self.assertEqual(self.logs.getvalue(),'')

    def test_cli_absolute_paths_bootstrap_once_and_sigterm_releases_owned_root(self):
        root=Path(self.tmp.name)/'cli-workspace'
        command=[sys.executable,'-m','pentest.workspace','--root',str(root)]
        env=__import__('os').environ.copy(); env['PYTHONPATH']=str(Path(__file__).resolve().parents[1]/'lib')
        bad=subprocess.run(command[:-1]+['relative'],env=env,capture_output=True,timeout=5)
        self.assertNotEqual(bad.returncode,0); self.assertNotIn(b'Traceback',bad.stderr)
        child=subprocess.Popen(command,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            line=child.stdout.readline().decode().strip()
            self.assertRegex(line,r'^http://127\.0\.0\.1:[0-9]+/#[A-Za-z0-9_-]{40,}$')
            child.terminate(); out,err=child.communicate(timeout=8)
            self.assertEqual(child.returncode,0,(out,err)); self.assertEqual(out,b''); self.assertEqual(err,b'')
            from pentest.workspace import Workspace
            with Workspace(root): pass
        finally:
            if child.poll() is None: child.kill()
            child.communicate()

    def test_close_pauses_active_engine_before_waiting_on_http_test_transport(self):
        self.start_http(owns_workspace=True); self.session()
        assets=self.ok('POST','/api/assets/preview',dict(text=self.origin+'/wait\n'+self.origin+'/two',format='lines'))['preview']['assets']
        snap=self.prepare(assets=assets); rid=snap['run']['id']; p='/api/runs/'+rid
        first=next(a for a in snap['plan']['actions'] if a['target'].endswith('/wait'))
        self.ok('POST',p+'/messages',dict(request_id=uuid.uuid4().hex,kind='prioritize',text='Wait first',action_ids=[first['id']]))
        self.ok('POST',p+'/approve',dict(plan_revision=snap['plan']['revision'],action_ids=[a['id'] for a in snap['plan']['actions']],actor='operator'))
        self.ok('POST',p+'/start',{}); self.assertTrue(self.entered.wait(3))
        entered,release=threading.Event(),threading.Event()
        result=[]
        def bounded_test(_): entered.set(); release.wait(4); return dict(status='ok')
        with mock.patch.object(self.ws.models,'test',side_effect=bounded_test):
            call=threading.Thread(target=lambda:result.append(self.request('POST','/api/models/'+str(uuid.uuid4())+'/test',{})))
            call.start(); self.assertTrue(entered.wait(3))
            closed=threading.Thread(target=self.http.close); started=time.monotonic(); closed.start()
            deadline=started+2
            while not self.ws._closed and time.monotonic()<deadline: time.sleep(.01)
            self.assertTrue(self.ws._closed,'HTTP transport join must not postpone engine pause')
            self.assertTrue(closed.is_alive())
            self.release.set(); release.set(); call.join(5); closed.join(5)
            self.assertFalse(call.is_alive()); self.assertFalse(closed.is_alive())
            self.assertLess(time.monotonic()-started,5)
        self.assertEqual(len(self.hits),1)
        self.assertEqual(self.ws.store.get_run(rid)['status'],'paused')
        self.assertFalse(self.http._workers)

    def test_close_retains_root_during_admitted_write_and_rejects_queued_write(self):
        from pentest.workspace import Workspace
        from pentest.workspace_store import WorkspaceError
        self.start_http(owns_workspace=True); self.session()
        assets=self.ok('POST','/api/assets/preview',dict(text=self.origin+'/',format='lines'))['preview']['assets']
        data=dict(name='Write fixture',goal='Only local writes',assets=assets)
        entered,release=threading.Event(),threading.Event(); results=[]; errors=[]
        original=self.ws.store.save_draft
        def delayed(*args,**kwargs): entered.set(); release.wait(3); return original(*args,**kwargs)
        def call(): results.append(self.request('POST','/api/tasks',dict(data=data)))
        def close():
            try: self.http.close()
            except Exception as exc: errors.append(exc)
        with mock.patch.object(self.ws.store,'save_draft',side_effect=delayed):
            first=threading.Thread(target=call); first.start(); self.assertTrue(entered.wait(2))
            second=threading.Thread(target=call); second.start(); time.sleep(.1)
            closer=threading.Thread(target=close); closer.start(); time.sleep(.2)
            try:
                self.assertFalse(self.ws._closed,'local write must drain before releasing engine ownership')
                with self.assertRaises(WorkspaceError): Workspace(self.root)
            finally: release.set()
            first.join(5); second.join(5); closer.join(5)
            self.assertFalse(closer.is_alive()); self.assertFalse(first.is_alive()); self.assertFalse(second.is_alive())
        self.assertEqual(errors,[])
        self.assertEqual(sorted(r[0] for r in results),[200,503])
        self.assertEqual(len(self.ws.store.list_drafts()),1)
        self.assertFalse(self.http._workers)
        with Workspace(self.root): pass

    def test_write_drain_timeout_is_incomplete_and_keeps_workspace_owned(self):
        from pentest import workspace_http as adapter
        from pentest.workspace import Workspace
        from pentest.workspace_store import WorkspaceError
        self.start_http(owns_workspace=True); self.session()
        assets=self.ok('POST','/api/assets/preview',dict(text=self.origin+'/',format='lines'))['preview']['assets']
        entered,release=threading.Event(),threading.Event(); original=self.ws.store.save_draft
        results=[]
        def delayed(*args,**kwargs): entered.set(); release.wait(3); return original(*args,**kwargs)
        with mock.patch.object(self.ws.store,'save_draft',side_effect=delayed), mock.patch.object(adapter,'WRITE_DRAIN_SECONDS',.05):
            call=threading.Thread(target=lambda:results.append(self.request('POST','/api/tasks',dict(data=dict(name='Slow write',goal='Local',assets=assets)))))
            call.start(); self.assertTrue(entered.wait(2))
            try:
                with self.assertRaises(WorkspaceError): self.http.close()
                self.assertFalse(self.ws._closed); self.assertFalse(self.http._closed_http)
                with self.assertRaises(WorkspaceError): Workspace(self.root)
            finally: release.set(); call.join(4)
        self.http.close(); self.assertTrue(self.ws._closed); self.assertFalse(self.http._workers)
        self.assertEqual(results[0][0],200)

    def test_close_from_listener_thread_avoids_shutdown_deadlock(self):
        self.start_http(owns_workspace=True)
        requested=threading.Event()
        def service_action():
            if not requested.is_set(): requested.set(); self.http.close()
        with mock.patch.object(self.http,'service_actions',side_effect=service_action):
            self.assertTrue(requested.wait(2)); self.http_thread.join(3)
            self.assertFalse(self.http_thread.is_alive())
            self.http.close()
        self.assertTrue(self.ws._closed); self.assertFalse(self.http._workers)


if __name__=='__main__': unittest.main()

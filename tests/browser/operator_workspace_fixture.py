"""Trusted, synthetic-only browser harness. Never imported by production entry points."""
import argparse
import http.client
import http.server
import json
import os
from pathlib import Path
import signal
import sys
import threading
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'lib'))
from pentest.models import ModelProfiles
from pentest.workspace import Workspace
from pentest.workspace_http import create_server

SYNTHETIC_KEY = 'sapper-browser-synthetic-key-only'
TARGET_PORT = 9551
MODEL_PORT = 9552
PURPOSES = ('probe', 'plan', 'analyze', 'guidance', 'review')
PATHS = ('/alpha', '/beta', '/slow', '/guided', '/failure')


def write_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=True, indent=2), encoding='utf-8')
    temporary.replace(path)


class FixtureServer(http.server.ThreadingHTTPServer):
    # Owned request threads are joined on server_close, including slow requests.
    daemon_threads = False
    block_on_close = True

    def handle_error(self, request, client_address):
        pass  # No raw requests/headers/exceptions in ordinary logs.


class OperatorFixture:
    def __init__(self, home, *, port=8876, container_listen=False):
        if port == 8765:
            raise ValueError('8765 is reserved for the unrelated viewer')
        self.home = Path(home).resolve()
        self.state = self.home / 'fixture'
        self.state.mkdir(parents=True, exist_ok=True)
        self.port = port
        self.container_listen = container_listen
        self.target_origin = 'http://127.0.0.1:9551'
        self.model_origin = 'http://127.0.0.1:9552'
        self.lock = threading.RLock()
        self.stopping = threading.Event()
        self.release = threading.Event()
        self.servers = []; self.threads = []
        self.http = self.ws = None
        self.data = json.loads((self.state/'records.json').read_text()) if (self.state/'records.json').exists() else dict(
            version=1, generation=0, target_hits=[], model_calls=[], emitted_fact_ids=[], guided_run_ids=[])
        self.data.setdefault('guided_run_ids', [])
        self.barrier = dict(armed=False, pending=False)
        self.fail_next = None
        self.last_control = None

    @property
    def origin(self):
        return 'http://127.0.0.1:'+str(self.port)

    def profile(self, bad=False):
        return dict(name='Synthetic browser model', provider='custom', base_url=self.model_origin+('/bad' if bad else '/good'),
                    model='fixture-model', api_key=SYNTHETIC_KEY, timeout_seconds=5, max_output_tokens=2048)

    def records(self):
        with self.lock:
            return json.loads(json.dumps(self.data))

    def metadata(self):
        with self.lock:
            hits = self.data['target_hits']; calls = self.data['model_calls']
            return dict(version=1, origin=self.origin, generation=self.data['generation'],
                target_origin=self.target_origin, model_good_base=self.model_origin+'/good', model_bad_base=self.model_origin+'/bad',
                synthetic_key=SYNTHETIC_KEY, targets={p[1:]:self.target_origin+p for p in PATHS},
                counts=dict(target_total=len(hits), model_total=len(calls),
                    target_by_path={p:sum(h['path']==p for h in hits) for p in PATHS},
                    model_by_purpose={p:sum(c['purpose']==p for c in calls) for p in PURPOSES}),
                barrier=dict(self.barrier), fail_next=self.fail_next)

    def persist(self):
        # Every caller holds the RLock; counters are independent of Workspace state.
        write_json(self.state/'records.json', self.data)
        write_json(self.state/'metadata.json', self.metadata())

    def control(self, command, purpose=None):
        with self.lock:
            if command == 'arm' and purpose is None:
                if self.barrier['pending']: raise ValueError('barrier already pending')
                self.release.clear(); self.barrier['armed'] = True
            elif command == 'release' and purpose is None:
                self.release.set(); self.barrier['armed'] = False
            elif command == 'fail_next' and purpose in PURPOSES:
                self.fail_next = purpose
            else:
                raise ValueError('unsupported fixture control')
            self.persist()

    def _control_loop(self):
        control_file = self.state/'control.json'
        while not self.stopping.wait(.05):
            try:
                request = json.loads(control_file.read_text())
                if set(request) != {'id','command','purpose'} or request['id'] == self.last_control:
                    continue
                uuid.UUID(request['id'])
                self.control(request['command'], request['purpose'])
                self.last_control = request['id']
                write_json(self.state/'control-ack.json', dict(id=self.last_control, ok=True))
            except (FileNotFoundError, ValueError, TypeError, KeyError):
                continue

    def _listen(self, port, handler):
        server = FixtureServer(('127.0.0.1', port), handler)
        self.servers.append(server)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval':.05})
        self.threads.append(thread); thread.start()

    def start(self):
        owner = self
        class Target(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self): self.observe()
            def do_HEAD(self): self.observe()
            def observe(self):
                self.connection.settimeout(30)
                path = self.path if self.path in PATHS else '__rejected__'
                status = 503 if path == '/failure' else 404 if path == '__rejected__' else 200
                with owner.lock:
                    wait = path == '/slow' and owner.barrier['armed']
                    if wait: owner.barrier.update(armed=False, pending=True)
                    owner.data['target_hits'].append(dict(sequence=len(owner.data['target_hits'])+1,
                        generation=owner.data['generation'], method=self.command, path=path, status=status, at=time.time()))
                    owner.persist()
                if wait:
                    owner.release.wait(25)
                    with owner.lock:
                        owner.barrier['pending'] = False; owner.persist()
                body = (b'SYNTHETIC EXPOSURE MARKER: training fixture only\n'
                        b'<script>window.syntheticInjected=true</script><img src=x onerror=alert(1)>') if path == '/alpha' else b'Synthetic fixture observation only'
                self.send_response(status); self.send_header('Content-Length', str(len(body))); self.end_headers()
                if self.command == 'GET':
                    try: self.wfile.write(body)
                    except (BrokenPipeError, ConnectionResetError): pass

        class Provider(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def reply(self, status, value):
                raw=json.dumps(value).encode()
                self.send_response(status); self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(raw))); self.end_headers()
                try: self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError): pass
            def do_POST(self):
                self.connection.settimeout(5)
                # Reject arbitrary keys without reading, recording or echoing them.
                if self.headers.get('Authorization') != 'Bearer '+SYNTHETIC_KEY:
                    self.reply(401, {'error':'synthetic fixture key required'}); return
                if self.path not in ('/good/chat/completions','/bad/chat/completions'):
                    self.reply(404, {'error':'fixed fixture route required'}); return
                try:
                    size=int(self.headers['Content-Length'])
                    if not 0 < size <= 1048576: raise ValueError()
                    payload=json.loads(self.rfile.read(size))
                    content=payload['messages'][-1]['content']
                    context=None if content=='Reply OK.' else json.loads(content)
                    purpose='probe' if context is None else context['purpose']
                    if purpose not in PURPOSES: raise ValueError()
                    if context is not None and set(context) != {'role','purpose','draft','scope','policy','history','guidance','observations','findings'}: raise ValueError()
                    selected_model=payload['model']
                    if not isinstance(selected_model,str) or len(selected_model)>128: raise ValueError()
                except (ValueError, TypeError, KeyError):
                    self.reply(400, {'error':'invalid fixture request'}); return
                with owner.lock:
                    failure=self.path.startswith('/bad/') or owner.fail_next==purpose
                    if owner.fail_next==purpose: owner.fail_next=None
                    owner.data['model_calls'].append(dict(sequence=len(owner.data['model_calls'])+1,
                        generation=owner.data['generation'], purpose=purpose, context=context,
                        model=selected_model, status=429 if failure else 200, at=time.time()))
                    proposal=None if failure else owner.proposal(context)
                    owner.persist()
                if failure:
                    self.reply(429, {'error':'synthetic provider failure '+SYNTHETIC_KEY}); return
                self.reply(200, dict(model=selected_model, choices=[dict(message=dict(content='OK' if context is None else json.dumps(proposal)))],
                    usage=dict(prompt_tokens=3,completion_tokens=2,total_tokens=5)))
        try:
            # Workspace root lock also prevents two fixtures sharing durable state.
            models=ModelProfiles(self.home/'models', allow_http_loopback=True)
            self.ws=Workspace(self.home/'workspace', models=models)
            self._listen(TARGET_PORT, Target); self._listen(MODEL_PORT, Provider)
            self.http=create_server(workspace=self.ws, owns_workspace=True, port=self.port, container_listen=self.container_listen)
            self.port=self.http.server_port
            with self.lock:
                self.data['generation']+=1; self.persist()
            private=self.state/'bootstrap.url'
            private.write_text(self.origin+'/#'+self.http.bootstrap_token, encoding='utf-8'); private.chmod(0o600)
            # Controls from previous generations must never be replayed.
            (self.state/'control.json').unlink(missing_ok=True)
            thread=threading.Thread(target=self.http.serve_forever, kwargs={'poll_interval':.05})
            self.threads.append(thread); thread.start()
            thread=threading.Thread(target=self._control_loop); self.threads.append(thread); thread.start()
            self.readiness()
            return self
        except BaseException:
            self.close(); raise

    def proposal(self, context):
        if context is None: return None
        purpose=context['purpose']
        result=dict(summary='Synthetic fixture observations only', gaps=['Manual security assessment remains'])
        if purpose == 'plan':
            actions=[]; assets=context['draft']['assets']
            if context['guidance']:
                rid=context['guidance'][0]['run_id']
                if rid not in self.data['guided_run_ids'] and any('/guided' in g['text'] for g in context['guidance']) and not any(
                    e['target']==self.target_origin+'/guided' for o in context['observations'] for e in o['evidence']):
                    actions=[dict(asset_id=assets[0]['id'], target=self.target_origin+'/guided',tool='http_get',role='Scout',
                        description='Guided synthetic observation',risk=2,evidence_gap=1)]
                    self.data['guided_run_ids'].append(rid)
            else:
                for index, asset in enumerate(assets):
                    if asset['target'] in [self.target_origin+p for p in PATHS]:
                        actions.append(dict(asset_id=asset['id'],target=asset['target'],tool='http_get',role='Scout' if index%2==0 else 'Soldier',
                            description='Observe synthetic fixture',risk=2,evidence_gap=1))
            result['actions']=actions
        elif purpose=='review':
            suggestions=[]
            for case in context['findings']:
                originals=case['evidence']; targets={e['target'] for e in originals}; receipts={e['receipt_id'] for e in originals}
                fresh=next((e for o in context['observations'] if o['valid'] for e in o['evidence']
                    if {e['target']}==targets and e['receipt_id'] not in receipts and e['started_at']>=max(old['finished_at'] for old in originals)),None)
                if fresh:
                    suggestions.append(dict(finding_id=case['id'],evidence_id=fresh['id'],outcome='confirmed',
                        note='Synthetic marker seen in a later independent exact-target receipt; advisory only.'))
            result['review_suggestions']=suggestions
        else:
            candidates=[]
            for observation in context['observations']:
                fid=observation['fact_id']
                if observation['valid'] and fid not in self.data['emitted_fact_ids'] and any(
                    e['target']==self.target_origin+'/alpha' and 'SYNTHETIC EXPOSURE MARKER' in e['excerpt'] for e in observation['evidence']):
                    candidates.append(dict(fact_id=fid,title='Synthetic exposure marker',severity='low',
                        description='The synthetic alpha response contains the training exposure marker.',
                        impact='Training-only demonstration of evidence-backed candidate review.',
                        reproduction='Approve and execute GET '+self.target_origin+'/alpha; inspect the verified receipt.',
                        remediation='Remove the synthetic marker before using this fixture as ordinary content.',cwe='CWE-200',operator_note='Synthetic fixture; requires independent operator review.'))
                    self.data['emitted_fact_ids'].append(fid)
            result['findings']=candidates
        return result

    def readiness(self):
        """Real login and read-only API requests; never create profiles/tasks/calls."""
        before=self.metadata()['counts']
        def request(method,path,body=None,headers=None):
            conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
            try:
                conn.request(method,path,json.dumps(body).encode() if body else None,headers or {})
                response=conn.getresponse(); data=json.loads(response.read())
                if response.status!=200: raise RuntimeError('inert readiness failed')
                return data, dict(response.getheaders())
            finally: conn.close()
        data,headers=request('POST','/api/session',dict(token=self.http.bootstrap_token),{'Origin':self.origin,'Content-Type':'application/json'})
        cookie=headers['Set-Cookie'].split(';')[0]
        for path in ('/api/session','/api/models','/api/tasks'):
            request('GET',path,headers={'Cookie':cookie})
        if before!=self.metadata()['counts']: raise RuntimeError('readiness unexpectedly made calls')
        with self.lock:
            write_json(self.state/'ready.json',dict(version=1,generation=self.data['generation'],authenticated=True,inert=True))
        return self.metadata()

    def close(self):
        self.stopping.set(); self.release.set()
        if self.http is not None:
            self.http.close(); self.http=None
        elif self.ws is not None:
            self.ws.close()
        for server in self.servers:
            server.shutdown(); server.server_close()
        for thread in self.threads:
            thread.join(30)
            if thread.is_alive(): raise RuntimeError('fixture thread did not stop')
        self.servers=[]; self.threads=[]; self.ws=None
        (self.state/'bootstrap.url').unlink(missing_ok=True)
        (self.state/'ready.json').unlink(missing_ok=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home',type=Path,default=Path('/state'))
    parser.add_argument('--port',type=int,default=8876)
    parser.add_argument('--container-listen',action='store_true')
    parser.add_argument('--control',choices=('arm','release','fail_next'))
    parser.add_argument('--purpose',choices=PURPOSES)
    args=parser.parse_args()
    if args.control:
        if (args.control=='fail_next') != bool(args.purpose): parser.error('purpose required only for fail_next')
        state=args.home/'fixture'; request=dict(id=uuid.uuid4().hex,command=args.control,purpose=args.purpose)
        write_json(state/'control.json',request)
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            try:
                if json.loads((state/'control-ack.json').read_text())['id']==request['id']: return
            except (FileNotFoundError,ValueError,KeyError): pass
            time.sleep(.05)
        raise RuntimeError('fixture control acknowledgement timed out')
    stopping=threading.Event()
    for sig in (signal.SIGINT,signal.SIGTERM): signal.signal(sig, lambda *_: stopping.set())
    fixture=OperatorFixture(args.home,port=args.port,container_listen=args.container_listen)
    try:
        fixture.start(); print('Synthetic operator fixture ready: '+fixture.origin,flush=True)
        stopping.wait()
    finally: fixture.close()


if __name__=='__main__': main()

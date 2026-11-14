"""Hosted lifecycle and browser-runtime contracts; no external service mutation."""
import base64
import json
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from board import Board
from cloud_server import Sessions, make_cloud_server
from analysis_server import AnalysisSession
from search_gate import SearchGate, GAME
from notation import san_for_move
from web_runtime import DIRECTORY, PREFIX


class LeaseTests(unittest.TestCase):
    def test_only_abandoned_clients_are_cancelled(self):
        clock=[0.0];sessions=Sessions(clock=lambda:clock[0],job_lease=90)
        old,game,_=sessions.session(None)
        live,other,_=sessions.session(None)
        analysis=game.analysis();analysis.active=True
        other.analysis().active=True
        epoch=analysis.epoch
        clock[0]=85;sessions.session(live)
        clock[0]=95;sessions.cancel_abandoned_jobs()
        self.assertFalse(analysis.active)
        self.assertGreater(analysis.epoch,epoch)
        self.assertTrue(other.analysis().active)

    def test_expired_session_cancels_work_before_eviction(self):
        clock=[0.0];sessions=Sessions(ttl=20,clock=lambda:clock[0])
        sid,game,_=sessions.session(None)
        game.analysis().active=True
        clock[0]=21;sessions.session(sid)
        self.assertFalse(game.analysis().active)

    def test_stale_tab_cannot_cancel_a_new_job(self):
        a=AnalysisSession(threading.Lock(),background=False)
        a.active=True;old=a.epoch
        a.epoch+=1
        a.stop(expected_epoch=old)
        self.assertTrue(a.active)
        a.stop(expected_epoch=a.epoch)
        self.assertFalse(a.active)


class HostedDeploymentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv=make_cloud_server(0,host='127.0.0.1',public_host='127.0.0.1',
            auth_user='test',auth_password='render-unit-test-password',secure=False)
        cls.thread=threading.Thread(target=cls.srv.serve_forever,daemon=True);cls.thread.start()
        cls.url='http://127.0.0.1:'+str(cls.srv.server_port)
        cls.auth='Basic '+base64.b64encode(b'test:render-unit-test-password').decode()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown();cls.srv.server_close();cls.thread.join(timeout=2)

    def request(self,path,data=None,cookie=None,method=None):
        headers={'Authorization':self.auth,'Origin':self.url}
        if cookie:headers['Cookie']=cookie
        if data is not None:
            headers['Content-Type']='application/json';data=json.dumps(data).encode()
        try:
            with urlopen(Request(self.url+path,data=data,headers=headers,method=method),timeout=5) as r:
                raw=r.read();return r.status,r.headers,raw
        except HTTPError as r:return r.code,r.headers,r.read()

    def test_config_does_not_expose_credentials(self):
        code,headers,body=self.request('/deployment-config.js')
        self.assertEqual(code,200);self.assertIn(b'0.9.2',body)
        self.assertNotIn(b'render-unit-test-password',body)
        self.assertEqual(headers['Cache-Control'],'no-store')

    def test_runtime_mime_csp_and_head_are_correct(self):
        if not (DIRECTORY/'pyodide.asm.wasm').exists():
            self.skipTest('Run tools/prepare_web_runtime.py for runtime HTTP tests.')
        code,headers,body=self.request(PREFIX+'pyodide.asm.wasm',method='HEAD')
        self.assertEqual(code,200);self.assertEqual(body,b'')
        self.assertEqual(headers['Content-Type'],'application/wasm')
        self.assertGreater(int(headers['Content-Length']),1000000)
        self.assertIn('immutable',headers['Cache-Control'])
        self.assertIn("'wasm-unsafe-eval'",headers['Content-Security-Policy'])
        self.assertIn('HttpOnly',headers.get('Set-Cookie','')) if headers.get('Set-Cookie') else None
        for name in ('../cloud_server.py','%2e%2e/cloud_server.py','manifest.json'):
            self.assertEqual(self.request(PREFIX+name)[0],404)

    def test_all_deep_presets_return_promptly_and_cancel(self):
        _,headers,raw=self.request('/api/analysis/state')
        cookie=headers['Set-Cookie'].split(';',1)[0]
        for seconds in (60,180,300,600):
            start=time.monotonic()
            status,_,raw=self.request('/api/analysis/start',dict(deep=True,seconds=seconds),cookie)
            self.assertEqual(status,200)
            data=json.loads(raw)
            self.assertLess(time.monotonic()-start,2)
            self.assertEqual(data['deep']['budget'],seconds)
            stopped=json.loads(self.request('/api/analysis/stop',{},cookie)[2])
            self.assertFalse(stopped['active'])

    def test_shutdown_cancels_active_sessions(self):
        srv=make_cloud_server(0,host='127.0.0.1',public_host='127.0.0.1',
            auth_user='test',auth_password='another-test-password',secure=False)
        _,game,_=srv.sessions.session(None)
        game.analysis().active=True
        srv.server_close()
        self.assertFalse(game.analysis().active)

    def test_blueprint_only_targets_new_test_service(self):
        source=Path('render.yaml').read_text()
        self.assertIn('name: tal-lab-chess-v092-test',source)
        self.assertNotIn('name: tal-lab-chess\n',source)
        self.assertIn('branch: development/render-test-v092',source)
        self.assertIn('autoDeployTrigger: "off"',source)
        self.assertIn('sync: false',source)


if __name__=='__main__':unittest.main()

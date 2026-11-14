import json
import threading
import time
from http.client import HTTPConnection
from web_server import make_server

server = make_server(0)
threading.Thread(target=server.serve_forever,daemon=True).start()
c=HTTPConnection('127.0.0.1',server.server_address[1],timeout=5)
def request(path, data=None):
    c.request('GET' if data is None else 'POST',path, None if data is None else json.dumps(data),
              {'Content-Type':'application/json'})
    r=c.getresponse()
    body=r.read()
    assert r.status==200,(r.status,body)
    return json.loads(body)
try:
    before = request('/api/analysis/state')
    started = request('/api/analysis/start',dict(deep=True,seconds=600,
                      expected_epoch=before['epoch'],expected_fen=before['fen']))
    assert started['active'] and started['deep']['budget']==600
    for _ in range(100):
        progress=request('/api/analysis/state')
        if progress['completed']:
            break
        time.sleep(.04)
    assert progress['active'] and progress['completed']['depth'] >= 1
    stop=request('/api/analysis/stop',{})
    assert not stop['active'] and stop['status']=='stopped'
    fast=request('/api/analysis/start',dict(min_depth=1,max_depth=2,seconds=10,multipv=3))
    assert fast['deep'] is None
    for _ in range(100):
        state=request('/api/analysis/state')
        if not state['active']:
            break
        time.sleep(.04)
    assert len(state['completed']['candidates'])==3
    print('HTTP: 600-second request, live depth, cancellation, subsequent fast MultiPV 3')
finally:
    c.close()
    server.shutdown()
    server.server_close()

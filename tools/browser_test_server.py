"""Ephemeral authenticated cloud server for real-browser tests, never Render."""
import json
import os
from pathlib import Path
import signal
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cloud_server import make_cloud_server

server=make_cloud_server(0,host='127.0.0.1',public_host='127.0.0.1',
    auth_user='browser-test',auth_password=os.environ['TAL_BROWSER_TEST_PASSWORD'],secure=False)
def stop(*_):raise KeyboardInterrupt
signal.signal(signal.SIGTERM,stop)
print(json.dumps({'port':server.server_port}),flush=True)
try:server.serve_forever(poll_interval=.1)
except KeyboardInterrupt:pass
finally:server.server_close()

"""Development preview ONLY. Render continues to use cloud_server.py with auth."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from http.server import ThreadingHTTPServer
from web_server import WebHandler, Game
from cloud_server import CloudHandler
p=argparse.ArgumentParser();p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=3000);p.add_argument('--strictPort',action='store_true');args=p.parse_args()
class Preview(CloudHandler):
    do_GET=WebHandler.do_GET
    do_POST=WebHandler.do_POST
    game=Game()
    _host_allowed = WebHandler._host_allowed
    _origin_allowed = WebHandler._origin_allowed
server=ThreadingHTTPServer((args.host,args.port),Preview);server.daemon_threads=True
server.serve_forever()

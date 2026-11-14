"""Pinned, optional same-origin Pyodide assets (no third-party server packages)."""
from pathlib import Path
import shutil

VERSION = '0.27.7'
PREFIX = f'/runtime/pyodide/v{VERSION}/'
CDN = f'https://cdn.jsdelivr.net/pyodide/v{VERSION}/full/'
DIRECTORY = Path(__file__).resolve().parent / 'web' / 'runtime' / f'pyodide-{VERSION}'
FILES = {'pyodide.js':'application/javascript; charset=utf-8',
         'pyodide.asm.js':'application/javascript; charset=utf-8',
         'pyodide.asm.wasm':'application/wasm',
         'python_stdlib.zip':'application/zip',
         'pyodide-lock.json':'application/json',
         'THIRD_PARTY_NOTICES.txt':'text/plain; charset=utf-8',
         'PYODIDE-LICENSE.txt':'text/plain; charset=utf-8',
         'PYTHON-LICENSE.txt':'text/plain; charset=utf-8'}


class RuntimeFile:
    """Send large immutable runtime assets with bounded per-request memory."""
    def __init__(self, path):
        self.path = path
        self.size = path.stat().st_size

    def __len__(self):
        return self.size

    def write_to(self, destination):
        with self.path.open('rb') as source:
            shutil.copyfileobj(source, destination, length=64*1024)


def public_config():
    import os
    from version import VERSION as engine_version
    base = os.environ.get('TAL_PYODIDE_BASE', CDN)
    if base not in (PREFIX, CDN):
        raise ValueError('TAL_PYODIDE_BASE must be the pinned same-origin path or pinned CDN.')
    default = os.environ.get('TAL_DEFAULT_COMPUTE', 'server')
    if default not in ('local','server','auto'):
        raise ValueError('TAL_DEFAULT_COMPUTE must be local, server or auto.')
    return dict(version=engine_version, runtime_base=base, default_compute=default,
                site_label=os.environ.get('TAL_SITE_LABEL','Tal Lab'),
                revision=os.environ.get('RENDER_GIT_COMMIT','')[:40])


def require_runtime(config):
    if config['runtime_base']==PREFIX:
        missing = [name for name in FILES if not (DIRECTORY/name).is_file()]
        if missing:
            raise ValueError('Browser runtime is missing. Run python tools/prepare_web_runtime.py first.')

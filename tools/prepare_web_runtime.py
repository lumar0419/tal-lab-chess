"""Fetch unmodified pinned browser runtime at build time; no client installs.

Validates npm SHA-512 integrity before extracting an explicit file allowlist.
The runtime is intentionally ignored by Git. Render runs this during its build.
"""
import base64
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from web_runtime import DIRECTORY, VERSION

URL = f'https://registry.npmjs.org/pyodide/-/pyodide-{VERSION}.tgz'
INTEGRITY = 'RUSVJlhQdfWfgO9hVHCiXoG+nVZQRS5D9FzgpLJ/VcgGBLSAKoPL8kTiOikxbHQm1kRISeWUBdulEgO26qpSRA=='
ASSETS = ('pyodide.js','pyodide.asm.js','pyodide.asm.wasm','python_stdlib.zip','pyodide-lock.json')
LICENSES = {
    'PYODIDE-LICENSE.txt':f'https://raw.githubusercontent.com/pyodide/pyodide/{VERSION}/LICENSE',
    'PYTHON-LICENSE.txt':'https://raw.githubusercontent.com/python/cpython/v3.12.7/LICENSE',
}


def download(url):
    with urllib.request.urlopen(url,timeout=90) as response:
        data=response.read(32*1024*1024+1)
    if len(data)>32*1024*1024:
        raise ValueError('Runtime download exceeded the build limit.')
    return data


def main():
    raw=download(URL)
    if base64.b64encode(hashlib.sha512(raw).digest()).decode()!=INTEGRITY:
        raise SystemExit('Pyodide archive integrity mismatch; build stopped.')
    DIRECTORY.mkdir(parents=True,exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
        for name in ASSETS:
            member=archive.getmember('package/'+name)
            if not member.isfile():raise ValueError('Unexpected runtime archive entry')
            (DIRECTORY/name).write_bytes(archive.extractfile(member).read())
    for name,url in LICENSES.items():
        (DIRECTORY/name).write_bytes(download(url))
    notices=(ROOT/'deploy'/'THIRD_PARTY_NOTICES.txt').read_bytes()
    (DIRECTORY/'THIRD_PARTY_NOTICES.txt').write_bytes(notices)
    manifest=dict(version=VERSION,archive=URL,sha512=INTEGRITY,
        files={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
               for p in DIRECTORY.iterdir() if p.is_file() and p.name!='manifest.json'})
    (DIRECTORY/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(f'Prepared verified Pyodide {VERSION} browser runtime ({len(ASSETS)} assets).')


if __name__=='__main__':main()

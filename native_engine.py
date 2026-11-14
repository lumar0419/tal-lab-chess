"""Explicit optional backend. Example: python native_engine.py uci

Also supports cloud_server, web_server, deep_analysis and research modules.
Never silently uses a stale binary or changes browser/Pyodide imports.
"""
import hashlib
import json
from pathlib import Path
import runpy
import sys


def activate():
    root = Path(__file__).resolve().parent
    native = root/'build/native'
    manifest = native/'manifest.json'
    if not manifest.is_file():
        raise SystemExit('Build native modules first: python tools/build_native.py build_ext --build-lib build/native')
    data = json.loads(manifest.read_text())
    if data['cache_tag'] != sys.implementation.cache_tag or data['python'] != sys.version.split()[0]:
        raise SystemExit('Native Python ABI differs. Rebuild the native modules.')
    for source, expected in data['sources'].items():
        if hashlib.sha256((root/source).read_bytes()).hexdigest() != expected:
            raise SystemExit(f'Stale native module: {source} changed. Rebuild before use.')
    if any(name in sys.modules for name in ('board','evaluate','search')):
        raise RuntimeError('Select the backend before importing engine modules.')
    sys.path.insert(0, str(native))
    import importlib.machinery
    for name in ('board','evaluate','search'):
        spec = importlib.machinery.PathFinder.find_spec(name, [str(native)])
        if spec is None or not isinstance(spec.loader, importlib.machinery.ExtensionFileLoader):
            raise SystemExit(f'Missing compiled module: {name}. Rebuild before use.')


def main():
    if len(sys.argv)<2:
        raise SystemExit(__doc__)
    activate()
    target = sys.argv.pop(1)
    runpy.run_module(target, run_name='__main__', alter_sys=True)


if __name__=='__main__':
    main()

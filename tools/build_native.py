"""Optional Cython acceleration of the SAME Python sources, never in-place.

Install Cython==3.1.8 and setuptools first, then run:
  python tools/build_native.py build_ext --build-lib build/native
Requires a C compiler (MSVC Build Tools on Windows). CPython only.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import sys

from Cython.Build import cythonize
from setuptools import Extension, setup

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
SOURCES = ('board.py', 'evaluate.py', 'search.py')
if platform.python_implementation() != 'CPython' or sys.platform == 'emscripten':
    raise SystemExit('Use the portable Python engine on this runtime.')
extensions = [Extension(Path(p).stem, [p]) for p in SOURCES]
source_hashes = {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES}
setup(name='tal-lab-native', version='0.9.3',
      ext_modules=cythonize(extensions, build_dir='build/cython',
          compiler_directives={'language_level':3, 'annotation_typing':False,
                               'binding':True, 'infer_types':False}))
destination = ROOT/'build/native'
destination.mkdir(parents=True, exist_ok=True)
if source_hashes != {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES}:
    raise SystemExit('Sources changed during compilation. Rebuild before use.')
(destination/'manifest.json').write_text(json.dumps({
    'implementation':'Tal Lab / Cython', 'python':platform.python_version(),
    'platform':platform.platform(), 'cache_tag':sys.implementation.cache_tag,
    'sources':source_hashes
}, indent=2)+'\n')

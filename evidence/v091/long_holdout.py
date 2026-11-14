import json
from pathlib import Path
suite=json.loads(Path('evidence-v091/holdout.json').read_text())
Path('evidence-v091/holdout-long.json').write_text(json.dumps(
    [r for r in suite if r['suite'] in ('long_sacrifice','forced_mate')],indent=2)+'\n')

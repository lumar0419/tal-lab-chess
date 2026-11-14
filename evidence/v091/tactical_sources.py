from pathlib import Path
import json
src=json.loads(Path('evidence-speed089/fixed-suite.json').read_text())
Path('evidence-v091/development.json').write_text(json.dumps(src,indent=2)+'\n')

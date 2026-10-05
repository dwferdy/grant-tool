import json, glob
from pathlib import Path
from engine.models import Rubric, Application
ROOT = Path(__file__).resolve().parent.parent
def load_rubric(): return Rubric.model_validate(json.loads((ROOT/"data/rubric.json").read_text()))
def load_applications():
    return {a.id: a for a in (Application.model_validate(json.loads(Path(f).read_text()))
            for f in sorted(glob.glob(str(ROOT/"data/applications/*.json"))))}

"""Run the AI checks for every application (or the ids given) and cache the results.
Usage:  python scripts/run_ai_checks.py [A01 A02 ...]"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.loader import load_rubric, load_applications
from engine.ai_checks import run_ai_checks, api_available
from engine.assess import assess, outcome

if not api_available():
    sys.exit("No ANTHROPIC_API_KEY found. Put it in .env first.")
rb, apps = load_rubric(), load_applications()
for aid in sys.argv[1:] or apps:
    run_ai_checks(apps[aid], rb, call_api=True)
    cells = assess(apps[aid], rb)
    print(f"{aid}: {outcome(rb, {r: c.verdict for r, c in cells.items()})}",
          " ".join(f"{r}={c.verdict.value}" for r, c in cells.items() if c.verdict.value not in ("met", "not_applicable")))

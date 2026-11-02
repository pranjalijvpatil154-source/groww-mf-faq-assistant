"""Post-deploy smoke checks for the /api/ask serverless pipeline (local run)."""
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv(Path(__file__).parent.parent / ".env")   # local .env, git-ignored
from api.ask import ask

tests = [
    ("How is my KYC validated?", "answer"),
    ("What is the weather in Mumbai today?", "refusal-NO_SOURCE"),
    ("Tell me a joke about cats", "refusal-NO_SOURCE"),
    ("Who do I contact for grievances on a Groww fund?", "answer"),
    ("What does the riskometer show for schemes?", "answer|pointer"),
]
for q, exp in tests:
    r = ask(q)
    state = r.get("verdict", r.get("mode"))
    print(f"[{exp:20s}] -> {r['kind']:7s} {state} | {(r.get('text') or '')[:70]}")

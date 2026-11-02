"""Calibrate the /api/ask retrieval threshold in the gemini-embedding space.

Embeds probe questions (RETRIEVAL_QUERY) and reports top-1 cosine score
against data/index/gemini_vectors.json (RETRIEVAL_DOCUMENT vectors).
Use the printed scores to pick a threshold separating in-corpus from
out-of-corpus questions.
"""
import json
import math
import os
import sys
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).parent.parent
load_dotenv(BASE / ".env")
KEY = os.getenv("LLM_API_KEY", "").strip()
EMBED_MODEL = "gemini-embedding-001"

vectors = json.loads((BASE / "data" / "index" / "gemini_vectors.json")
                     .read_text(encoding="utf-8"))["vectors"]

PROBES = [
    # in-corpus (should retrieve)
    ("in", "How is my KYC validated?"),
    ("in", "Where can I download the KIM of Groww Largecap Fund?"),
    ("in", "Who do I contact for grievances on a Groww fund?"),
    ("in", "What is the consolidated account statement and how do I get it?"),
    ("in", "Where do I find the scheme information document?"),
    ("in", "What risk level does the riskometer show?"),
    ("in", "How do new KYC regulations affect existing investors?"),
    ("in", "How do mutual funds work for beginners?"),
    # edge / out-of-corpus (should NOT retrieve)
    ("out", "What was the NAV yesterday of Groww Largecap Fund?"),
    ("out", "Recommend me the best fund for my retirement goals"),
    ("out", "Tell me a joke about cats"),
    ("out", "Who is the ABC of XYZ company?"),
    ("out", "How do I open a savings bank account?"),
    ("out", "What is the weather in Mumbai today?"),
]


def embed(text: str) -> list[float]:
    body = {"model": f"models/{EMBED_MODEL}", "taskType": "RETRIEVAL_QUERY",
            "content": {"parts": [{"text": text}]}}
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{EMBED_MODEL}:embedContent?key={KEY}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())["embedding"]["values"]


def cosine(a, b):
    ab = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return ab / (na * nb) if na and nb else 0.0


results = {"in": [], "out": []}
# NOTE: in-corpus min 0.6906, out-of-corpus max 0.6886 (Nov 2026 sweep).
# Threshold 0.65 sits below the in-corpus floor with margin, while refusing
# obviously off-topic probes (weather 0.57, jokes 0.52, savings account 0.59).
# Borderline out-probes still pass retrieval but hit the grounded REFUSE ->
# pointer layer inside _generate(), which is the correct behavior anyway.
for label, q in PROBES:
    v = embed(q)
    scores = sorted(((cosine(v, row["vector"]), row["chunk_id"]) for row in vectors),
                    reverse=True)
    top = scores[0]
    results[label].append(top[0])
    print(f"[{label:3s}] {top[0]:.4f}  ({top[1]})  {q[:58]}")

in_min = min(results["in"])
out_max = max(results["out"])
print(f"\nin-corpus min={in_min:.4f}   out-of-corpus max={out_max:.4f}")
mid = (in_min + out_max) / 2
if in_min > out_max:
    print(f"clean separation - suggested threshold ~ {mid:.2f} (midpoint)")
else:
    print(f"WARNING: overlapping distributions - midpoint {mid:.2f} imperfect")

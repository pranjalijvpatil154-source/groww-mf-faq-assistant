"""Re-embed approved corpus with the Gemini embedding API (model space match
with query-time embedding on Vercel, where sentence-transformers can't run).

Output: data/index/gemini_vectors.json  (31 x dim vectors + metadata)
Run locally (needs .env LLM_API_KEY):   py ingest/embed_gemini.py
"""
import json
import os
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).parent.parent
load_dotenv(BASE / ".env")

EMBED_MODEL = "gemini-embedding-001"
KEY = os.getenv("LLM_API_KEY", "").strip()
if not KEY:
    raise SystemExit("LLM_API_KEY missing in .env")

chunks = [json.loads(l) for l in
          (BASE / "data" / "index" / "chunks.jsonl").open(encoding="utf-8")]

out = []
for c in chunks:
    body = {"model": f"models/{EMBED_MODEL}",
            "taskType": "RETRIEVAL_DOCUMENT",
            "content": {"parts": [{"text": c["text"]}]}}
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{EMBED_MODEL}:embedContent?key={KEY}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                vec = json.loads(r.read())["embedding"]["values"]
            break
        except Exception as e:
            if attempt == 2:
                raise
            print(f"  retry {c['chunk_id']}: {e}")
            time.sleep(3)
    out.append({"chunk_id": c["chunk_id"], "url": c["url"],
                "publisher": c["publisher"], "doc_type": c["doc_type"],
                "scheme": c["scheme"], "last_updated": c["last_updated"],
                "vector": vec})
    print(f"{c['chunk_id']}: dim={len(vec)}")

payload = {"model": EMBED_MODEL,
           "dim": len(out[0]["vector"]),
           "count": len(out),
           "built_at": datetime.now(timezone.utc).isoformat(),
           "note": "vectors are RE-model-space; query must embed with same model",
           "vectors": out}
target = BASE / "data" / "index" / "gemini_vectors.json"
target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
print(f"\nwrote {len(out)} embeddings -> {target.name}")

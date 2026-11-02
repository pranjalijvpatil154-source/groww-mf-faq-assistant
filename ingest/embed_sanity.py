"""Step 5 sanity check — semantic smoke test of the built vectors."""
import json

import numpy as np
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")
V = np.load("data/index/vectors.npy")
chunks = [json.loads(l) for l in open("data/index/chunks.jsonl", encoding="utf-8")]

for q in ["What is the expense ratio of a fund?", "minimum SIP amount",
          "how to download statement", "lock-in period ELSS"]:
    qv = model.encode([q], normalize_embeddings=True)[0]
    scores = V @ qv
    top = scores.argsort()[::-1][:2]
    print("Q:", q)
    for i in top:
        c = chunks[i]
        print("   %.3f  %s  (%s)" % (scores[i], c["chunk_id"], c["url"]))

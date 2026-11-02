"""Step 7 — Retrieval logic (Layer 3, ARCHITECTURE.md).

Corpus-only, no re-ranker, no open-web fallback (PRD FR1):
question -> embed with the SAME embedder (read from manifest.json) ->
FAISS top-k -> scheme pre-filter -> score threshold -> chunks or NO_SOURCE.

NO_SOURCE must travel straight to the refusal path — it is never handed
to the LLM as an answerable case (IMPLEMENTATION.md Step 7).

Run probe calibration check:  py tests/retrieval_probe.py
"""
import json
from functools import lru_cache
from pathlib import Path

import faiss
import numpy as np

BASE = Path(__file__).parent.parent
IDX_DIR = BASE / "data" / "index"
FAISS_PATH = IDX_DIR / "faiss.index"
META_PATH = IDX_DIR / "meta.jsonl"
CHUNKS_PATH = IDX_DIR / "chunks.jsonl"

TOP_K = 4
SCORE_THRESHOLD = 0.35   # calibrated in Step 7 (tests/retrieval_probe.py sweep:
                         # hits 17/18, NO_SOURCE 6/6; sole miss documented in probe file)

# scheme detection for the pre-filter (text-level, since ledger `scheme = all`)
SCHEME_TOKENS = {
    "elss": "Groww ELSS Tax Saver Fund",
    "largecap": "Groww Largecap Fund",
    "large cap": "Groww Largecap Fund",
    "multicap": "Groww Multicap Fund",
    "multi cap": "Groww Multicap Fund",
    "value fund": "Groww Value Fund",
    "smallcap": "Groww Small cap Fund",
    "small cap": "Groww Small cap Fund",
    "liquid": "Groww Liquid Fund",
    "money market": "Groww Money Market Fund",
    "overnight": "Groww Overnight Fund",
    "gilt": "Groww Gilt Fund",
    "arbitrage": "Groww Arbitrage Fund",
}

SCHEME_NOT_IN_CORPUS = {  # mentioned schemes outside our approved corpus
    "hdfc", "sbi", "icici", "parag", "axis", "kotak", "nippon", "bitcoin",
    "crypto", "stock", "shares", "trading",
}


def _mentions_scheme(chunk_text: str, scheme: str) -> bool:
    """The canonical name without the 'Groww' prefix must appear in the chunk."""
    if not scheme:
        return True
    core = scheme.replace("Groww", "").strip().lower()
    return core in chunk_text.lower()

@lru_cache(maxsize=1)
def _load() -> tuple:
    manifest = json.loads((IDX_DIR / "manifest.json").read_text(encoding="utf-8"))
    model = __import__("sentence_transformers").SentenceTransformer(manifest["embedder"])
    index = faiss.read_index(str(FAISS_PATH))
    meta = [json.loads(l) for l in META_PATH.open(encoding="utf-8")]
    chunks = [json.loads(l) for l in CHUNKS_PATH.open(encoding="utf-8")]
    return model, index, meta, chunks


def _score(question: str) -> tuple[str | None, np.ndarray]:
    """Detect a named scheme; returns (canonical_scheme, question_vector)."""
    model, _, _, _ = _load()
    q = question.lower()
    scheme = next((canon for token, canon in SCHEME_TOKENS.items() if token in q), None)
    vec = model.encode([question], normalize_embeddings=True)[0]
    return scheme, vec


def retrieve(question: str) -> dict:
    """Full Step-7 pipeline. Returns:

    OK:       {"verdict": "OK", "chunks": [{score, chunk, url, ...}],
               "scheme_matched": str|None}
    NO_SOURCE:{"verdict": "NO_SOURCE", "reason": "..."}   (goes to refusals.py)
    """
    q = question.lower()
    if any(tok in q for tok in SCHEME_NOT_IN_CORPUS):
        return {"verdict": "NO_SOURCE",
                "reason": "question is outside the approved corpus scope"}
    scheme, vec = _score(question)

    _, index, meta, chunks = _load()
    D, I = index.search(np.asarray([vec], dtype="float32"), TOP_K)

    results = []
    for score, i in zip(D[0], I[0]):
        c = chunks[i]
        if scheme and not _mentions_scheme(c["text"], scheme):
            continue   # scheme pre-filter: chunk must actually mention it
        results.append({"score": float(score), "chunk": c,
                        "url": meta[i]["url"], "source_id": meta[i]["source_id"],
                        "last_updated": c["last_updated"]})
    if not results:
        return {"verdict": "NO_SOURCE",
                "reason": f"no approved-page chunk matched scheme {scheme!r}" if scheme
                else "no approved-page chunk matched"}

    best = results[0]
    if best["score"] < SCORE_THRESHOLD:
        return {"verdict": "NO_SOURCE",
                "reason": f"best score {best['score']:.3f} below threshold {SCORE_THRESHOLD}"}
    return {"verdict": "OK", "chunks": results[:TOP_K],
            "scheme_matched": scheme}


if __name__ == "__main__":
    demo = ["how do I download the capital gains statement?",
            "what is the minimum amount required to invest in mutual funds?",
            "how is my KYC validated?",
            "what is the lock-in period of the ELSS scheme?"]
    for question in demo:
        r = retrieve(question)
        if r["verdict"] == "OK":
            print(f"{question}\n  OK  top={r['chunks'][0]['score']:.3f} "
                  f"{r['chunks'][0]['source_id']}")
        else:
            print(f"{question}\n  NO_SOURCE ({r['reason']})")
        print("-" * 72)

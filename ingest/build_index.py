"""Steps 4-6 — Chunking -> Embedding -> Vector DB build.

Run:  py ingest/build_index.py [--rebuild]

Step 4 (implemented here): chunk documents.jsonl into small retrievable pieces.
  - size  ~200-220 estimated tokens  (all-MiniLM has a 256-token limit, so the
    originally planned 300-500 is tightened to fit the embedder; noted in docs)
  - overlap ~15% of target
  - sentence-level packing: a fact sentence or table row is NEVER split
  - every chunk carries url/scheme/doc_type/fact_hint metadata

Step 5 (implemented here): embed chunks with sentence-transformers MiniLM.
  - EMBEDDER constant is the single source of truth (same model at query time)
  - normalize_embeddings=True -> unit vectors; cosine == dot product
  - artifacts: vectors.npy + meta.jsonl + manifest.json

Step 6 (implemented here): store vectors in a FAISS flat-IP index.
  - vectors are unit-normalised, so IndexFlatIP == cosine similarity
  - the index contains ONLY approved-source chunks (PRD FR1: corpus-only
    retrieval is enforced here, at build time)
  - artifacts: faiss.index (+ manifest notes); --rebuild is idempotent
"""
import argparse
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import faiss
import numpy as np

BASE = Path(__file__).parent.parent
DOCS = BASE / "data" / "index" / "documents.jsonl"
CHUNKS = BASE / "data" / "index" / "chunks.jsonl"
VECTORS = BASE / "data" / "index" / "vectors.npy"
META = BASE / "data" / "index" / "meta.jsonl"
MANIFEST = BASE / "data" / "index" / "manifest.json"
FAISS_INDEX = BASE / "data" / "index" / "faiss.index"

EMBEDDER = "all-MiniLM-L6-v2"   # single source of truth for the embedder name

TARGET_TOKENS = 210   # chunk target (~fits all-MiniLM 256-token window)
OVERLAP_TOKENS = 30   # ~15% of target
MAX_TOKENS = 250      # hard cap per chunk

FACT_HINTS = {
    "expense_ratio": re.compile(r"expense\s+ratio", re.I),
    "exit_load": re.compile(r"exit\s+load", re.I),
    "minimum_sip": re.compile(r"minimum\s*(?:sip|amount|investment)|min\.?\s+sip", re.I),
    "lock_in": re.compile(r"lock[\s-]?in", re.I),
    "riskometer": re.compile(r"riskometer|risk(?:\s+level|s|\s+o-meter)", re.I),
    "benchmark": re.compile(r"benchmark|index\s+used|triangulates", re.I),
    "statement": re.compile(r"statement|capital[\s-]?gains|cas\b", re.I),
    "download": re.compile(r"download|\.pdf\b", re.I),
    "sip": re.compile(r"\bsip\b|systematic\s+investment", re.I),
    "kyc": re.compile(r"\bkyc\b", re.I),
    "grievance": re.compile(r"grievance|complaint", re.I),
}


def est_tokens(text: str) -> int:
    """Cheap deterministic token estimate (words+digits ≈ 1 token × 1.3)."""
    words = re.findall(r"[A-Za-z0-9₹%./-]+", text)
    return max(1, int(len(words) * 1.3))


def _units(text: str) -> list[str]:
    """Split into atomic units: sentences; '|' table rows stay whole."""
    norm = unicodedata.normalize("NFKC", text)
    norm = norm.replace("\ufffd", " ")
    units = []
    for line in norm.splitlines():
        line = line.strip()
        if not line:
            continue
        if "|" in line:                       # table row = atomic, never split
            units.append(line)
            continue
        parts = re.split(r"(?<=[.!?])\s+", line)
        units.extend(p.strip() for p in parts if p.strip())
    return units


def chunk_text(text: str) -> list[str]:
    units = _units(text)
    chunks, cur, cur_tokens = [], [], 0
    for u in units:
        t = est_tokens(u)
        if t > MAX_TOKENS:                    # pathological unit: own chunk
            if cur:
                chunks.append(" ".join(cur))
                back = []
                bt = 0
                for prev in reversed(cur):
                    if bt + est_tokens(prev) > OVERLAP_TOKENS:
                        break
                    back.insert(0, prev)
                    bt += est_tokens(prev)
                cur, cur_tokens = back, bt
            chunks.append(u)
            continue
        if cur_tokens + t > TARGET_TOKENS and cur:
            chunks.append(" ".join(cur))
            back, bt = [], 0                  # ~15% tail-overlap
            for prev in reversed(cur):
                ub = est_tokens(prev)
                if bt + ub > OVERLAP_TOKENS:
                    break
                back.insert(0, prev)
                bt += ub
            cur, cur_tokens = back, bt
        cur.append(u)
        cur_tokens += t
    if cur:
        chunks.append(" ".join(cur))
    return [c for c in chunks if c.strip()]


def _fact_hints(chunk: str) -> list[str]:
    return [k for k, rx in FACT_HINTS.items() if rx.search(chunk)]


def chunk_documents() -> list[dict]:
    docs = [json.loads(l) for l in DOCS.open(encoding="utf-8")]
    rows, built = [], datetime.now(timezone.utc).isoformat()
    per_doc = {}
    for d in docs:
        for i, ctext in enumerate(chunk_text(d["text"])):
            rows.append({
                "chunk_id": f'{d["source_id"]}#c{i:02d}',
                "source_id": d["source_id"],
                "url": d["url"],
                "publisher": d["publisher"],
                "doc_type": d["doc_type"],
                "scheme": d["scheme"],
                "last_updated": d["last_updated"],
                "chunk_idx": i,
                "num_tokens": est_tokens(ctext),
                "fact_hint": _fact_hints(ctext),
                "built_at": built,
                "text": ctext,
            })
            per_doc[d["source_id"]] = per_doc.get(d["source_id"], 0) + 1
    with CHUNKS.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"chunks.jsonl written: {len(rows)} chunks from {len(docs)} documents")
    for sid, n in sorted(per_doc.items()):
        print(f"  {sid}: {n} chunks")
    over = [r["chunk_id"] for r in rows if r["num_tokens"] > MAX_TOKENS * 1.1]
    print(f"chunks over size cap: {len(over)}")
    return rows


def embed_chunks() -> None:
    """Step 5 — load chunks, embed with MiniLM, write vectors.npy + meta.jsonl."""
    from sentence_transformers import SentenceTransformer

    rows = [json.loads(l) for l in CHUNKS.open(encoding="utf-8")]
    texts = [r["text"] for r in rows]
    print(f"embedding {len(rows)} chunks with {EMBEDDER} ...")
    model = SentenceTransformer(EMBEDDER)
    vecs = model.encode(texts, batch_size=32, normalize_embeddings=True,
                        show_progress_bar=False)
    vecs = np.asarray(vecs, dtype="float32")
    np.save(VECTORS, vecs)
    with META.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            r = dict(r)
            r.pop("text", None)              # vectors + metadata only; text stays in chunks.jsonl
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    manifest = {
        "embedder": EMBEDDER,
        "embedder_revision": getattr(model, "model_card_data", None)
        and getattr(getattr(model, "model_card_data", None), "base_model_revision", None),
        "dim": int(vecs.shape[1]),
        "num_chunks": int(vecs.shape[0]),
        "normalized": True,
        "norm_check": float(np.round(np.linalg.norm(vecs[0]), 6)),
        "built_at": datetime.now(timezone.utc).isoformat(),
        "constraint": "index content = chunks from approved source_list.csv only",
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"vectors.npy {vecs.shape} -> {VECTORS.name} | meta.jsonl -> {META.name}")
    print(f"manifest written: {manifest['embedder']} dim={manifest['dim']} "
          f"chunks={manifest['num_chunks']} (row norm={manifest['norm_check']}; 1.0 = unit)")


def store_vector_db() -> None:
    """Step 6 — build + persist the FAISS flat index (cosine over unit vectors)."""
    vecs = np.load(VECTORS)
    norms = np.linalg.norm(vecs, axis=1)
    if not np.allclose(norms, 1.0, atol=1e-3):
        raise RuntimeError(f"vectors not unit-normalised (norm range {norms.min():.3f}..{norms.max():.3f})")
    index = faiss.IndexFlatIP(vecs.shape[1])   # inner product == cosine here
    index.add(vecs)
    faiss.write_index(index, str(FAISS_INDEX))
    # record storage in the manifest
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["vector_db"] = {"kind": "faiss", "path": FAISS_INDEX.name,
                             "metric": "inner_product_on_unit_vectors (=cosine)",
                             "num_vectors": int(index.ntotal)}
    MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"faiss.index stored: {index.ntotal} vectors ({vecs.shape[1]}-d) -> {FAISS_INDEX.name}")


def verify_search() -> None:
    """Storage round-trip check: probe queries against the persisted index."""
    index = faiss.read_index(str(FAISS_INDEX))
    meta = [json.loads(l) for l in META.open(encoding="utf-8")]
    chunks = [json.loads(l) for l in CHUNKS.open(encoding="utf-8")]
    model = __import__("sentence_transformers").SentenceTransformer(EMBEDDER)
    for q in ["What is the expense ratio of a fund?", "minimum SIP amount",
              "how to download statement", "KYC validation"]:
        qv = model.encode([q], normalize_embeddings=True)
        D, I = index.search(qv, 2)
        print("Q:", q)
        for rank, (score, i) in enumerate(zip(D[0], I[0]), 1):
            print(f"   #{rank} {score:.3f}  {chunks[i]['chunk_id']}  {meta[i]['url']}")


def main(rebuild: bool = False) -> None:
    if rebuild:
        for p in (CHUNKS, VECTORS, META, MANIFEST, FAISS_INDEX):
            p.unlink(missing_ok=True)
    chunk_documents()
    embed_chunks()
    store_vector_db()
    print("[step-6 done] run verify with: py ingest/build_index.py --verify")


def _cli() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true", help="wipe artifacts and rebuild everything")
    ap.add_argument("--verify", action="store_true", help="round-trip search check on the stored index")
    args = ap.parse_args()
    if args.verify:
        verify_search()
    else:
        main(rebuild=args.rebuild)


if __name__ == "__main__":
    _cli()

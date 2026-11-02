"""Step 3 — Loading: read extracted text into one clean, validated document list.

Consumes:  data/raw/<source_id>.txt  (produced by fetch_pages.py)
           ingest/source_list.csv        (metadata + approved-URL allow-list)
Produces:  data/index/documents.jsonl    (the ONLY input for Step 4 chunking)

Pipeline (order matters):
  1. load .txt per approved source_id, repair encoding, tidy lines
  2. validate: text exists, >= MIN_CHARS, approved URL
  3. exact-duplicate drop (content hash)
  4. cross-document boilerplate removal  (nav/footer chrome duplicated on
     many pages): lines in >= 2/5 of docs are dropped from the TEXT
  5. near-duplicate drop on the REMAINING content (greedy, larger wins)
  6. emit documents.jsonl with metadata + cleaning stats

Run:  py ingest/load_docs.py
"""
import csv
import json
import re
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher
from hashlib import sha256
from pathlib import Path

BASE = Path(__file__).parent.parent
BUILD_TIME = datetime.now(timezone.utc).isoformat()
RAW = BASE / "data" / "raw"
SOURCE_LIST = Path(__file__).parent / "source_list.csv"
DOCS_OUT = BASE / "data" / "index" / "documents.jsonl"

MIN_CHARS = 200
BOILERPLATE_SHARE = 2 / 5
NEAR_DUP_THRESHOLD = 0.85
MIN_JUNK_LINE = 4  # ignore tiny generic fragments when scoring boilerplate


def _sha(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _safe_text(raw: str) -> str:
    raw = unicodedata.normalize("NFKC", raw)
    return raw.replace("\ufffd", " ")


def _tidy(text: str) -> str:
    out, seen = [], set()
    for ln in text.splitlines():
        ln = re.sub(r"\s+", " ", ln).strip()
        if not ln or ln in seen:
            continue
        seen.add(ln)
        out.append(ln)
    return "\n".join(out)


def load_sources() -> list[dict]:
    lines = [ln for ln in SOURCE_LIST.read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.startswith("#")]
    return list(csv.DictReader(lines))


def load_documents() -> dict:
    sources = load_sources()
    skipped, docs = [], []

    # 1-2 load + validate
    for meta in sources:
        sid = meta["source_id"]
        path = RAW / f"{sid}.txt"
        if not path.exists():
            skipped.append({"source_id": sid, "reason": "missing .txt (failed fetch)"})
            continue
        text = _tidy(_safe_text(path.read_text(encoding="utf-8")))
        if len(text) < MIN_CHARS:
            skipped.append({"source_id": sid, "reason": f"too short ({len(text)} chars)"})
            continue
        docs.append({"source_id": sid, **{k: meta[k] for k in
                     ("url", "publisher", "doc_type", "scheme", "last_updated")},
                     "text": text})

    # 3 exact duplicates
    unique, hashes = [], {}
    for d in docs:
        h = _sha(d["text"])
        if h in hashes:
            skipped.append({"source_id": d["source_id"],
                            "reason": f"exact duplicate of {hashes[h]}"})
            continue
        hashes[h] = d["source_id"]
        unique.append(d)

    # 4 global boilerplate (runs BEFORE similarity so chrome never counts)
    freq: dict[str, int] = {}
    for d in unique:
        for ln in set(d["text"].splitlines()):
            if len(ln) >= MIN_JUNK_LINE:
                freq[ln] = freq.get(ln, 0) + 1
    cutoff = max(2, int(len(unique) * BOILERPLATE_SHARE))
    boiler = {ln for ln, n in freq.items() if n >= cutoff and len(ln) > 8}
    for d in unique:
        kept_lines = [ln for ln in d["text"].splitlines() if ln not in boiler]
        d["boilerplate_chars_removed"] = len(d["text"]) - len("\n".join(kept_lines))
        d["text"] = "\n".join(kept_lines)

    # 5 near-duplicates on the cleaned text (greedy: bigger document wins)
    survivors = sorted(unique, key=lambda d: -len(d["text"]))
    kept = []
    for d in survivors:
        twin = next((k for k in kept
                     if SequenceMatcher(None, d["text"], k["text"]).ratio()
                     >= NEAR_DUP_THRESHOLD), None)
        if twin:
            skipped.append({"source_id": d["source_id"],
                            "reason": f"near-duplicate of {twin['source_id']} "
                                      f"(kept {twin['doc_type']} page, more content)"})
            continue
        kept.append(d)

    # 6 emit
    for d in kept:
        d["num_chars"] = len(d["text"])
        d["num_lines"] = d["text"].count("\n") + 1
        d["loaded_at"] = BUILD_TIME

    DOCS_OUT.parent.mkdir(parents=True, exist_ok=True)
    with DOCS_OUT.open("w", encoding="utf-8", newline="\n") as f:
        for d in kept:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    return {"loaded": len(kept), "skipped": skipped,
            "boilerplate_lines_dropped": len(boiler)}


def main() -> None:
    r = load_documents()
    print(f"documents.jsonl written: {r['loaded']} documents -> {DOCS_OUT.name}")
    print(f"boilerplate lines dropped globally: {r['boilerplate_lines_dropped']}")
    if r["skipped"]:
        print("skipped:")
        for s in r["skipped"]:
            print(f"  - {s['source_id']}: {s['reason']}")


if __name__ == "__main__":
    main()

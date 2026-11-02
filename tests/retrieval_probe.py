"""Step 7 runner — retrieval probe calibration (threshold sweep).

Reads probes from tests/retrieval_probe.md, runs app.retriever.retrieve at
several thresholds, reports hit/NO_SOURCE correctness, and recommends a
threshold with clean separation.

Run:  py tests/retrieval_probe.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import app.retriever as R  # noqa: E402

PROBE_FILE = Path(__file__).parent / "retrieval_probe.md"


def read_probes() -> list[tuple[str, str]]:
    probes = []
    for line in PROBE_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("q|"):
            _, question, expect = line.strip().split("|")
            probes.append((question.strip('"'), expect))
    return probes


def run(threshold: float) -> dict:
    R.SCORE_THRESHOLD = threshold
    hit_ok = hit_total = ns_ok = ns_total = 0
    failures = []
    for question, expect in read_probes():
        r = R.retrieve(question)
        if expect.startswith("hit:"):
            keyword = expect.split("hit:", 1)[1].lower()
            # generator receives the whole top-k set; any retrieved chunk
            # containing the fact keyword is a retrieval success
            ok = (r["verdict"] == "OK" and any(
                keyword in c["chunk"]["text"].lower() for c in r["chunks"]))
            hit_total += 1
            hit_ok += ok
            if not ok:
                top = r["chunks"][0]["source_id"] if r["verdict"] == "OK" else "NO_SOURCE"
                failures.append(f"want {expect!r} got {top} :: {question}")
        else:
            ns_total += 1
            if r["verdict"] == "NO_SOURCE":
                ns_ok += 1
            else:
                failures.append(f"want NO_SOURCE got "
                                f"{r['chunks'][0]['source_id']} "
                                f"(score {r['chunks'][0]['score']:.3f}) :: {question}")
    return {"threshold": threshold, "hits": f"{hit_ok}/{hit_total}",
            "no_source": f"{ns_ok}/{ns_total}", "score": hit_ok + ns_ok,
            "failures": failures}


def main() -> None:
    print("threshold sweep")
    results = [run(th) for th in (0.20, 0.25, 0.28, 0.30, 0.33, 0.35, 0.40, 0.45)]
    for r in results:
        print(f"  th={r['threshold']:.2f}  hits={r['hits']}  "
              f"NO_SOURCE={r['no_source']}")
    best = max(results, key=lambda r: (r["score"], r["threshold"]))
    print(f"\nrecommended threshold: {best['threshold']:.2f} "
          f"(hits={best['hits']}, NO_SOURCE={best['no_source']})")
    print("\nfailures at recommended threshold:")
    for f in best["failures"]:
        print(" ", f)
    if not best["failures"]:
        print("  none — clean separation")


if __name__ == "__main__":
    main()

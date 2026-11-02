"""Step 2 — Scraping: fetch ONLY the URLs listed in source_list.csv.

Policy (per requirement): fetch exactly the shared/approved links.
NEVER: follow internal links, crawl, or download PDF/other internal documents.

Run:  py ingest/fetch_pages.py
Output:
  data/raw/<source_id>.html  (raw cache)
  data/raw/<source_id>.txt   (extracted text)
  data/raw/fetch_report.json (per-row status + timestamp)
"""
import csv
import html as htmllib
import json
import re
import urllib.request
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError

BASE = Path(__file__).parent.parent
DATA = BASE / "data" / "raw"
SOURCE_LIST = Path(__file__).parent / "source_list.csv"

HEADERS = {"User-Agent": "Mozilla/5.0 (MF-FAQ-prototype; educational project)"}
TIMEOUT = 30


def read_sources() -> list[dict]:
    lines = [ln for ln in SOURCE_LIST.read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.startswith("#")]
    rows = list(csv.DictReader(lines))
    return [r for r in rows if r.get("url") and not r["url"].startswith("<")]


def fetch(url: str) -> tuple[str, bool]:
    """Single fetch, no redirects into other pages, no link extraction.

    Second value = used_fallback_ssl (cert verification was retried without
    a CA chain because the local machine lacks issuer certificates).
    """
    import ssl
    req = urllib.request.Request(url, headers=HEADERS)
    from urllib.error import URLError
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status}")
            return resp.read().decode("utf-8", errors="replace"), False
    except URLError as exc:
        if "CERTIFICATE" not in str(exc):
            raise
        ctx = ssl._create_unverified_context()  # last-resort retry; flagged in report
        req2 = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req2, timeout=TIMEOUT, context=ctx) as resp:
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status}")
            return resp.read().decode("utf-8", errors="replace"), True


def extract_text(raw_html: str) -> str:
    """Robust stdlib HTML->text (no external deps needed to run)."""
    # Prefer trafilatura when available, else fall back to stdlib extractor.
    try:
        import trafilatura  # type: ignore
        text = trafilatura.extract(raw_html, include_tables=True)
        return text or stdlib_extract(raw_html)
    except Exception:
        return stdlib_extract(raw_html)


def stdlib_extract(raw_html: str) -> str:
    """Keep table rows visible (| separator) so fee figures survive."""
    raw_html = re.sub(r"<(script|style|noscript|svg|head)[^>]*>.*?</\1>",
                      " ", raw_html, flags=re.S | re.I)
    raw_html = re.sub(r"</t[dh]>", " | ", raw_html, flags=re.I)
    raw_html = re.sub(r"</tr>", "\n", raw_html, flags=re.I)
    raw_html = re.sub(r"<br\s*/?>", "\n", raw_html, flags=re.I)
    raw_html = re.sub(r"</(p|div|li|h[1-6]|section|header|footer)>",
                      "\n", raw_html, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", raw_html)
    text = htmllib.unescape(text)
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    report, ok = [], 0
    for row in read_sources():
        sid, url = row["source_id"], row["url"]
        print(f"fetching {sid} -> {url}")
        try:
            raw, insecure = fetch(url)
        except (HTTPError, URLError, RuntimeError, TimeoutError) as exc:
            print(f"  !! FAILED: {exc}")
            report.append({"source_id": sid, "url": url,
                           "status": f"error: {exc}", "fetched_on": str(date.today())})
            continue
        (DATA / f"{sid}.html").write_text(raw, encoding="utf-8")
        (DATA / f"{sid}.txt").write_text(extract_text(raw), encoding="utf-8", newline="\n")
        ok += 1
        report.append({"source_id": sid, "url": url, "status": "ok", "bytes": len(raw),
                       "ssl_fallback": insecure,
                       "fetched_on": str(date.today())})
    (DATA / "fetch_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n{ok}/{len(report)} pages scraped -> {DATA}")


if __name__ == "__main__":
    main()

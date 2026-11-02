"""Step 8 — Tiny UI (Layer 1): welcome line, 3 examples, disclaimer.

Run:  streamlit run app/ui.py

Flow (ARCHITECTURE.md 5): input guardrail -> retriever -> generator ->
output guardrail -> render. Refusals short-circuit at L2/L5; anything that
answers shows ONE official citation + the date-stamp footer (FR3, FR4).

Stateless by design: no chat history, no session store, nothing persisted
(NFR1). Only plain text goes in the input box (FR7).
"""
import sys
from pathlib import Path

_HERE = Path(__file__).parent
PARENT = _HERE.parent
for p in (str(PARENT), str(_HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import guardrails  # noqa: E402
import generator  # noqa: E402
import refusals  # noqa: E402
from retriever import retrieve  # noqa: E402

SCHEMES = ("Groww Largecap Fund, Groww ELSS Tax Saver Fund, Groww Multicap "
           "Fund, Groww Liquid Fund and other Groww MF schemes documented on "
           "growwmf.in")

EXAMPLES = [
    "How do I download the capital gains statement?",
    "How is my KYC validated?",
    "What is the minimum amount required to invest in mutual funds?",
]

DISCLAIMER = (
    "This assistant answers factual questions about mutual fund scheme details "
    "using official public sources (AMC/SEBI/AMFI) only. It shows one source "
    "link for every answer. It does NOT give investment advice, does NOT "
    "comment on which fund to buy or sell, and does NOT compare or predict "
    "returns. "
    "Please read the official scheme documents before acting."
)


def ask(question: str) -> dict:
    """The full pipeline; returns a renderable payload, never raises."""
    try:
        verdict = guardrails.check_input(question)
        if verdict != "OK":
            link = (refusals.EDUCATIONAL_LINKS.get("PERFORMANCE")
                    if verdict == "PERFORMANCE_BLOCK"
                    else refusals.EDUCATIONAL_LINKS["SEBI_EDU"])
            return {"kind": "refusal", "text": refusals.refusal_text(verdict),
                    "link": link, "verdict": verdict}

        result = retrieve(question)
        if result["verdict"] != "OK":
            return {"kind": "refusal", "text": refusals.refusal_text("NO_SOURCE"),
                    "link": refusals.EDUCATIONAL_LINKS["DOC_HUB"],
                    "verdict": result["reason"][:120]}

        gen = generator.answer(question, result["chunks"])
        if gen.get("mode") == "REFUSE" or not gen.get("text"):
            return {"kind": "refusal", "text": refusals.refusal_text("NO_SOURCE"),
                    "link": refusals.EDUCATIONAL_LINKS["DOC_HUB"],
                    "verdict": "generator REFUSE"}

        approved = guardrails.approved_urls_from_csv(
            Path(__file__).parent.parent / "ingest" / "source_list.csv")
        ok, reason = guardrails.check_output(gen["text"], gen["citation_url"],
                                             gen["last_updated"], approved)
        if not ok:
            return {"kind": "refusal", "text": refusals.refusal_text("FALLBACK"),
                    "link": refusals.EDUCATIONAL_LINKS["DOC_HUB"],
                    "verdict": f"output blocked: {reason}"}

        footer = f"Last updated from sources: {gen['last_updated']}"
        return {"kind": "answer", "text": gen["text"],
                "footer": footer, "citation_url": gen["citation_url"],
                "mode": gen["mode"]}
    except Exception as exc:  # E8 — never a stack trace in the UI
        return {"kind": "refusal", "text": refusals.refusal_text("FALLBACK"),
                "link": refusals.EDUCATIONAL_LINKS["DOC_HUB"],
                "verdict": f"pipeline error: {exc}"}


def _answer_block(a: dict):
    import streamlit as st
    st.success(a["text"])
    st.caption(f"{a['footer']} · [Official source]({a['citation_url']})"
               + (" · zero-key extractive mode" if a["mode"] != "llm" else ""))
    st.caption("**Facts-only. No investment advice.**")


def _refusal_block(r: dict):
    import streamlit as st
    st.warning(r["text"])
    st.caption(f"See also: [{r['link']}]({r['link']})")
    st.caption("**Facts-only. No investment advice.**")


def run_ui():
    import streamlit as st
    st.set_page_config(page_title="Groww MF Facts-Only FAQ",
                       page_icon="📘", layout="centered")
    st.title("📘 Groww MF Facts-Only FAQ")
    st.markdown(
        f"Hi! I answer factual questions about **{SCHEMES}** — "
        "charges, KYC, statements, risk disclosures — using official public "
        "sources only.")

    st.markdown("**Try one of these:**")
    cols = st.columns(3)
    picked = None
    for col, example in zip(cols, EXAMPLES):
        if col.button(example, key=example[:24]):
            picked = example

    question = st.text_input("Ask a factual question:",
                             value=picked or "",
                             placeholder="e.g. How is my KYC validated?")
    st.caption("Facts-only. No investment advice.")

    if question.strip():
        a = ask(question.strip())
        if a["kind"] == "answer":
            _answer_block(a)
        else:
            _refusal_block(a)

    with st.expander("Disclaimer (what this can and cannot do)"):
        st.write(DISCLAIMER)


if __name__ == "__main__":
    run_ui()

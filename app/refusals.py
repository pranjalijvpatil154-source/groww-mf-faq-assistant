"""Step 8/9 — Deterministic refusal templates (refusals.py).

Every refusal is polite, short, facts-only, with EXACTLY ONE educational
link (PRD FR6, FR8). Keyed by guardrail verdict:

E1 PII_BLOCK          -> do not store, do not echo, explain scope
E2/E3 ADVICE_BLOCK    -> 1 SEBI/AMFI investor-education link
E4/E5 OOS/NO_SOURCE   -> "not in my approved sources" + wide disclaimer
E3' PERFORMANCE_BLOCK -> 1 link to the official factsheet
"""

TEMPLATES: dict[str, str] = {
    "PII_BLOCK": (
        "I don't use or store any personal details, so let's take those out. "
        "I can only answer factual questions about Groww Mutual Fund scheme "
        "documents. Facts-only. No investment advice."
    ),
    "ADVICE_BLOCK": (
        "I'm facts-only, so I can't suggest buying, selling or holding anything. "
        "For neutral guidance, SEBI and AMFI investor-education pages are a good "
        "start: {link}  Facts-only. No investment advice."
    ),
    "PERFORMANCE_BLOCK": (
        "I don't compute or compare returns. The official factsheet for this "
        "scheme carries the latest performance disclosure: {link}  "
        "Facts-only. No investment advice."
    ),
    "OOS_BLOCK": (
        "That's outside my scope — I only cover Groww Mutual Fund scheme "
        "documents (charges, KYC, statements, risk disclosures) from official "
        "public sources. Facts-only. No investment advice."
    ),
    "NO_SOURCE": (
        "I can't find this fact in my approved official sources, so I'd rather "
        "not answer than guess. Ask me about scheme fees, minimum SIP, exit "
        "load, lock-in, riskometer or statements. Facts-only. No investment advice."
    ),
    "FALLBACK": (
        "Something went wrong on my side. Please try another factual question. "
        "Facts-only. No investment advice."
    ),
}

EDUCATIONAL_LINKS = {
    # official allow-listed pages only (source_list.csv / growwmf.in)
    "SEBI_EDU": "https://investor.sebi.gov.in/",
    "AMFI_EDU": "https://www.mutualfundssahihai.com/en",
    "FACTSHEET": "https://growwmf.in/downloads/fact-sheet",
    "PERFORMANCE": "https://growwmf.in/downloads/scheme-performance",
    "DOC_HUB": "https://growwmf.in/downloads/kim",
}


def refusal_text(verdict: str) -> str:
    return TEMPLATES.get(verdict, TEMPLATES["FALLBACK"])

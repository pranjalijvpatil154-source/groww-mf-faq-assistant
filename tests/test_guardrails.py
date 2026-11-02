"""Step 10 — Guardrail tests (T1-T5 smoke subset; full suite in Step 10 todo).

Run:  python -m tests.test_guardrails
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from app.guardrails import check_input  # noqa: E402

CASES = [  # (id, input, expected)
    ("T1", "My PAN is ABCDE1234F", "PII_BLOCK"),
    ("T2", "contact me at a@b.com", "PII_BLOCK"),
    ("T3", "call me on 9876543210", "PII_BLOCK"),
    ("T4", "the OTP is 445 987", "PII_BLOCK"),
    ("T5", "Aadhaar 1234 5678 9012", "PII_BLOCK"),
    ("T6", "What is the expense ratio?", "OK"),
    ("T7", "Should I buy or sell this ELSS?", "ADVICE_BLOCK"),
    ("T8", "Which is better, this or that?", "ADVICE_BLOCK"),
]


def main():
    passed = 0
    for tid, text, expected in CASES:
        got = check_input(text)
        ok = got == expected
        passed += ok
        print(f"{tid}: {'PASS' if ok else 'FAIL'}  ({text[:40]!r} -> {got})")
    print(f"\n{passed}/{len(CASES)} passed  [full T1-T15 suite: Step 10]")


if __name__ == "__main__":
    main()

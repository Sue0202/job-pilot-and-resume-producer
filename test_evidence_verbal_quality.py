"""Focused tests for verbal generation quality (concise, non-repetitive, capability-based).

Run: python test_evidence_verbal_quality.py
"""

import re

import evidence_verbal as ev

_results = []
EX = ev.PERMISSION_GOV_EXAMPLE


def check(name, cond):
    _results.append((name, bool(cond)))
    print(f"{'PASS' if cond else 'FAIL'}: {name}")


def _bullet():
    return ev.generate_resume_bullet(
        EX["factual_context"], EX["impact_outcome"], role_family="Product Operations",
    )[0]


def _translation():
    return ev.generate_target_translation(
        EX["factual_context"], "Product Operations", impact_outcome=EX["impact_outcome"],
    )[0]


def test_bullet_no_major_repetition():
    b = _bullet()
    check("approval paths once", b.lower().count("approval paths") <= 1)
    check("exception handling once", b.lower().count("exception handling") <= 1)
    check("elevated-access once", b.lower().count("elevated-access") <= 1)
    check("no duplicate lifecycle clause", b.lower().count("structured lifecycle") <= 1)


def test_bullet_word_count():
    b = _bullet()
    wc = len(b.split())
    check("at least 25 words", wc >= 25)
    check("at most 45 words", wc <= 45)


def test_bullet_no_generic_filler():
    b = _bullet().lower()
    check("no supporting delivery needs", "supporting product operations delivery needs" not in b)
    check("no cross-functional filler", "cross-functional delivery" not in b)
    check("no stakeholder alignment filler", "stakeholder alignment in an enterprise context" not in b)


def test_translation_mentions_specific_capabilities():
    t = _translation().lower()
    check("mentions access governance theme", "access governance" in t or "approval workflow" in t)
    check("mentions lifecycle or enablement", "lifecycle" in t or "enablement" in t)
    check("no generic cross-functional boilerplate",
          "cross-functional delivery, workflow coordination, and stakeholder alignment" not in t)


def _false_system_claim(text, term):
    """Match standalone system claims, not substrings inside words like enterprise."""
    return bool(re.search(rf"\b{re.escape(term)}\b", text.lower()))


def test_translation_no_false_enterprise_system_claims():
    t = _translation().lower()
    for term in ("workday", "hris", "netsuite", "salesforce", "iam platform"):
        check(f"no false {term} claim", not _false_system_claim(t, term))
    check("no erp ownership claim", "erp ownership" not in t and "erp administration" not in t)


def test_bullet_no_false_enterprise_system_claims():
    b = _bullet().lower()
    for term in ("workday", "hris", "netsuite", "salesforce"):
        check(f"bullet no false {term}", term not in b)


def test_empty_facts_returns_error():
    text, err = ev.generate_resume_bullet("")
    check("empty bullet error", err is not None)
    check("empty bullet text", not text)


if __name__ == "__main__":
    test_bullet_no_major_repetition()
    test_bullet_word_count()
    test_bullet_no_generic_filler()
    test_translation_mentions_specific_capabilities()
    test_translation_no_false_enterprise_system_claims()
    test_bullet_no_false_enterprise_system_claims()
    test_empty_facts_returns_error()
    passed = sum(1 for _, ok in _results if ok)
    failed = [n for n, ok in _results if not ok]
    print(f"\n{passed}/{len(_results)} passed")
    if failed:
        print("FAILED:", ", ".join(failed))
        raise SystemExit(1)

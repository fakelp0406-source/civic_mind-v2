"""Screening of extracted document text before review (evidence for a person, not a guarantee).

``screen_pages`` looks for three things in each page's extracted text and reports them as
manifest findings for the reviewer. It never edits text and never decides anything itself.

* ``content.instruction_like`` - text addressed to a language model or assistant ("ignore the
  previous instructions", "system prompt", chat-role tags). Official documents rarely contain
  this; when they do, the reviewer must accept it as a caveat or exclude the pages.
* ``content.personal_data_suspected`` - e-mail addresses, Indian mobile numbers and
  Aadhaar-like 12-digit groups (a group of three years such as "2019 2020 2021", common in
  statistical tables, is not counted). Official contact details often match; the reviewer decides.
  **Matched values are never recorded**, only their kind and page numbers.
* ``content.non_english`` - pages where Devanagari, Kannada or Tamil letters are more than
  ``NON_LATIN_SHARE`` of all letters. Milestone 05 retrieval is English only.

Patterns are deliberately narrower than the question parser's: legal and policy text uses
words such as "instructions", "override" and "act as" in their ordinary sense.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

METHOD = (
    "extracted-text pattern screen docscreen@v2 (regular expressions per page; matched "
    "personal values are not recorded)"
)

INSTRUCTION_PATTERNS = (
    ("ignore_previous", r"\b(ignore|disregard|forget)\s+(all\s+|any\s+|the\s+|your\s+)?"
                        r"(previous|prior|above|earlier|preceding)\s+(instructions?|prompts?|"
                        r"rules|messages?|context)\b"),
    ("system_prompt", r"\bsystem\s+prompt\b"),
    ("model_address", r"\b(you\s+are\s+(now\s+)?(an?\s+|the\s+)?(\w+\s+){0,2}(ai|assistant|"
                      r"language\s+model|chatbot|llm)\b|as\s+an\s+ai\b|dear\s+(ai|assistant|"
                      r"language\s+model))"),
    # A role label followed by a directive anywhere in the text (chunks are single lines).
    ("role_directive", r"\b(system|assistant|developer)\s*:\s*(you\s|ignore\b|disregard\b|"
                       r"reveal\b|pretend\b|act\s+as\b|forget\b)"),
    ("chat_role_tag", r"<\s*/?\s*(system|assistant|user|instructions?)\s*>|^\s*(system|"
                      r"assistant)\s*:"),
    ("jailbreak", r"\b(jailbreak|developer\s+mode|dan\s+mode)\b"),
    ("override_rules", r"\b(override|bypass)\s+(the\s+|all\s+|your\s+)?(safety\s+|system\s+)?"
                       r"(rules|instructions|guardrails|policies)\b"),
    ("covert_output", r"\b(do\s+not|don't|never)\s+(cite|mention|reveal|disclose)\s+"
                      r"(this|these|the\s+source|your\s+instructions)\b"),
)  # fmt: skip

PERSONAL_PATTERNS = (
    ("email", r"\b[\w.+-]+@[\w-]+(\.[\w-]+)+\b"),
    ("mobile_number", r"(?<![\d-])(\+91[\s-]?|0)?[6-9]\d{9}(?![\d-])"),
    ("aadhaar_like", r"(?<!\d)\d{4}\s\d{4}\s\d{4}(?!\d)"),
)

SCRIPTS = {
    "devanagari": (0x0900, 0x097F),
    "tamil": (0x0B80, 0x0BFF),
    "kannada": (0x0C80, 0x0CFF),
}
NON_LATIN_SHARE = 0.2
MIN_LETTERS = 20


def _finding(code: str, severity: str, message: str, details: dict) -> dict:
    return {"code": code, "severity": severity, "message": message, "details": details}


def _scripts(text: str) -> dict[str, int]:
    counts = dict.fromkeys(SCRIPTS, 0)
    for ch in text:
        cp = ord(ch)
        for name, (lo, hi) in SCRIPTS.items():
            if lo <= cp <= hi:
                counts[name] += 1
                break
    return counts


def non_english(text: str) -> list[str]:
    """Non-Latin scripts that make up more than ``NON_LATIN_SHARE`` of the page's letters."""
    letters = sum(ch.isalpha() for ch in text)
    if letters < MIN_LETTERS:
        return []
    counts = _scripts(text)
    if sum(counts.values()) / letters <= NON_LATIN_SHARE:
        return []
    return sorted(name for name, n in counts.items() if n)


def _is_year(group: str) -> bool:
    return 1900 <= int(group) <= 2099


def _counts(kind: str, matched: str) -> bool:
    """Whether a match counts. Statistical tables print runs of years ("2019 2020 2021"),
    which have the shape of an Aadhaar number; a group made only of years is not counted."""
    if kind == "aadhaar_like":
        return not all(_is_year(g) for g in matched.split())
    return True


def screen_pages(pages: Iterable[tuple[int, str]]) -> list[dict]:
    """Findings for a document's pages (``(page_number, text)`` pairs, 1-based)."""
    instruction: dict[str, set[int]] = {}
    personal: dict[str, set[int]] = {}
    languages: dict[int, list[str]] = {}
    screened = 0
    for number, text in pages:
        screened += 1
        lower = text.lower()
        for name, pattern in INSTRUCTION_PATTERNS:
            if re.search(pattern, lower, re.MULTILINE):
                instruction.setdefault(name, set()).add(number)
        for name, pattern in PERSONAL_PATTERNS:
            if any(_counts(name, m.group()) for m in re.finditer(pattern, text)):
                personal.setdefault(name, set()).add(number)
        scripts = non_english(text)
        if scripts:
            languages[number] = scripts
    findings = []
    if instruction:
        findings.append(
            _finding(
                "content.instruction_like",
                "warning",
                "Text addressed to an AI system or assistant; accept as a caveat or exclude "
                "the pages before approval",
                {
                    "pages": sorted(set().union(*instruction.values())),
                    "patterns": {k: sorted(v) for k, v in sorted(instruction.items())},
                },
            )
        )
    if personal:
        findings.append(
            _finding(
                "content.personal_data_suspected",
                "warning",
                "Patterns that may be personal data (values not recorded); accept as official "
                "contact details or exclude the pages",
                {
                    "pages": sorted(set().union(*personal.values())),
                    "kinds": {k: sorted(v) for k, v in sorted(personal.items())},
                },
            )
        )
    if languages:
        findings.append(
            _finding(
                "content.non_english",
                "warning",
                "Pages mostly in a non-Latin script; retrieval is English only (exclude or "
                "accept as not retrievable)",
                {
                    "pages": sorted(languages),
                    "scripts": sorted(set().union(*map(set, languages.values()))),
                },
            )
        )
    findings.append(
        _finding(
            "content.screen",
            "info",
            "Extracted text screened" + ("" if findings else "; nothing matched"),
            {"method": METHOD, "pages_screened": screened},
        )
    )
    return findings


__all__ = [
    "INSTRUCTION_PATTERNS",
    "METHOD",
    "NON_LATIN_SHARE",
    "PERSONAL_PATTERNS",
    "non_english",
    "screen_pages",
]

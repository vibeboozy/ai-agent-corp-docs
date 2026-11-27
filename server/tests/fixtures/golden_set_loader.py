"""
ANCHOR: tests.fixtures.golden_set_loader
PURPOSE: Parse server/tests/fixtures/golden-set.md into structured cases.
Dependencies: re, pathlib
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_FIXTURE_PATH = Path(__file__).resolve().parent / "golden-set.md"

_FIELD_RE = re.compile(
    r"^- \*\*(?P<key>[^*]+):\*\*\s*`?(?P<val>.*?=`?)?\s*$",
    re.MULTILINE,
)
# Keys may wrap backticks around values.
_LINE_RE = re.compile(
    r"^- \*\*(?P<key>[^:]+):\*\*\s*(?P<val>.*)$"
)


@dataclass(frozen=True)
class GoldenCase:
    id: str
    scenario: str
    question: str
    expected_behavior: str
    expected_doc: str
    locator: str
    quote_snippet: str
    notes: str


def golden_set_path() -> Path:
    return _FIXTURE_PATH


def load_golden_cases(path: Path | None = None) -> list[GoldenCase]:
    """Load GS-01…GS-16 from the markdown fixture."""
    text = (path or _FIXTURE_PATH).read_text(encoding="utf-8")
    blocks = re.split(r"(?m)^## GS-", text)
    cases: list[GoldenCase] = []
    for block in blocks[1:]:
        body = "## GS-" + block
        fields: dict[str, str] = {}
        for line in body.splitlines():
            m = _LINE_RE.match(line.strip())
            if not m:
                continue
            key = m.group("key").strip().lower()
            val = m.group("val").strip()
            # Strip surrounding backticks / em-dash empties.
            if val.startswith("`") and val.endswith("`"):
                val = val[1:-1]
            if val in {"—", "-", "–"}:
                val = ""
            fields[key] = val
        case_id = fields.get("id", "")
        scenario = fields.get("scenario", "")
        question = fields.get("question", "")
        if not (case_id and scenario and question):
            continue
        cases.append(
            GoldenCase(
                id=case_id,
                scenario=scenario,
                question=question,
                expected_behavior=fields.get("expected_behavior", ""),
                expected_doc=fields.get("expected_doc", ""),
                locator=fields.get("locator", ""),
                quote_snippet=fields.get("quote_snippet", "").strip("«»\"'"),
                notes=fields.get("notes / traps", fields.get("notes", "")),
            )
        )
    return cases

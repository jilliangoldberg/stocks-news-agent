"""
Deterministic structural checks for a generated brief. No API calls.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict

from agent import get_holdings

EXPECTED_SECTIONS = [
    "top stories",
    "market impact",
    "portfolio impact",
    "opportunities & risks",
    "suggested actions",
]

SIGNAL_TAGS = ["[Watch]", "[Hold]", "[Caution]"]
DISCLAIMER = "These are probabilistic insights, not trading recommendations."

ADVICE_PATTERNS = [
    r"\byou should (buy|sell|short)\b",
    r"\b(buy|sell) now\b",
    r"\bstrong (buy|sell)\b",
    r"\bwill definitely\b",
    r"\bguaranteed (return|gain|profit|upside)s?\b",
    r"\bcan'?t lose\b",
]

# Uppercase tokens that look like tickers but are ordinary market acronyms.
COMMON_ACRONYMS = {
    "AI", "API", "CEO", "CFO", "CPI", "DOJ", "EM", "EPS", "ESG", "ETF", "EU", "EV", "EVS",
    "FED", "FOMC", "FTC", "GDP", "IPO", "IRA", "NYT", "PCE", "PPI", "QOQ", "SEC", "UK",
    "US", "USA", "USD", "YOY", "YTD", "ROTH", "OPEC", "IMF", "ECB", "BOJ", "GPU", "GPUS",
    "LLM", "M&A", "AND", "OR", "THE", "TBD", "ATH", "PE", "P/E", "DXY", "VIX", "WTI",
}

SECTION_HEADING = re.compile(r"^##\s*(\d)\.\s*(.+?)\s*$", re.MULTILINE)
TICKER_TOKEN = re.compile(r"\b[A-Z]{2,5}\b")


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""
    severity: str = "fail"  # "fail" or "warn"

    def to_dict(self) -> dict:
        return asdict(self)


def split_sections(brief: str) -> dict[int, str]:
    """Map section number -> body text (everything until the next ## N. heading)."""
    matches = list(SECTION_HEADING.finditer(brief))
    sections = {}
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(brief)
        sections[int(match.group(1))] = brief[match.end():end]
    return sections


def _strip_markup(text: str) -> str:
    return re.sub(r"[*_`]", "", text)


def check_sections_present(brief: str) -> CheckResult:
    headings = [
        (int(m.group(1)), _strip_markup(m.group(2)).strip().lower())
        for m in SECTION_HEADING.finditer(brief)
    ]
    expected = list(enumerate(EXPECTED_SECTIONS, 1))
    if headings == expected:
        return CheckResult("sections_present", True)
    missing = [f"{n}. {name}" for n, name in expected if (n, name) not in headings]
    return CheckResult(
        "sections_present", False,
        f"expected 5 sections in order; missing/misnamed: {missing or 'none'}; found: {headings}",
    )


def _holding_line(section_text: str, ticker: str) -> str | None:
    """The line that discusses this holding: prefer one that starts with the ticker."""
    pattern = re.compile(rf"\b{re.escape(ticker)}\b")
    candidates = [line for line in section_text.splitlines() if pattern.search(line)]
    for line in candidates:
        if _strip_markup(line).lstrip(" -•|").startswith(ticker):
            return line
    return candidates[0] if candidates else None


def check_holdings_covered(sections: dict[int, str], holdings: list[str]) -> CheckResult:
    section = sections.get(3, "")
    missing = [t for t in holdings if _holding_line(section, t) is None]
    if missing:
        return CheckResult("holdings_covered", False, f"missing from Portfolio impact: {missing}")
    return CheckResult("holdings_covered", True)


def check_signal_tags(sections: dict[int, str], holdings: list[str]) -> CheckResult:
    section = sections.get(3, "")
    problems = []
    for ticker in holdings:
        line = _holding_line(section, ticker)
        if line is None:
            continue  # reported by holdings_covered
        tags = re.findall(r"\[[A-Za-z ]+\]", _strip_markup(line))  # tolerates [**Hold**]
        valid = [t for t in tags if t in SIGNAL_TAGS]
        if len(valid) != 1 or len(tags) != 1:
            problems.append(f"{ticker}: {tags or 'no tag'}")
    if problems:
        return CheckResult("signal_tags_valid", False, "; ".join(problems))
    return CheckResult("signal_tags_valid", True)


def check_disclaimer(sections: dict[int, str]) -> CheckResult:
    normalized = " ".join(_strip_markup(sections.get(5, "")).split())
    if DISCLAIMER in normalized:
        return CheckResult("disclaimer_present", True)
    return CheckResult("disclaimer_present", False, "closing disclaimer missing from Suggested actions")


def check_no_definitive_advice(brief: str) -> CheckResult:
    hits = []
    for pattern in ADVICE_PATTERNS:
        hits += [m.group(0) for m in re.finditer(pattern, brief, re.IGNORECASE)]
    if hits:
        return CheckResult("no_definitive_advice", False, f"advice-like phrasing: {hits}")
    return CheckResult("no_definitive_advice", True)


def check_not_truncated(stop_reason: str | None) -> CheckResult:
    if stop_reason == "max_tokens":
        return CheckResult("not_truncated", False, "hit max_tokens; brief was cut off")
    return CheckResult("not_truncated", True)


def check_unknown_tickers(sections: dict[int, str], holdings: list[str], articles: list[dict]) -> CheckResult:
    article_text = " ".join(f"{a.get('title', '')} {a.get('summary', '')}" for a in articles)
    known = set(holdings) | set(TICKER_TOKEN.findall(article_text)) | COMMON_ACRONYMS
    text = " ".join(sections.get(n, "") for n in (3, 4, 5))
    unknown = sorted(set(TICKER_TOKEN.findall(text)) - known)
    if unknown:
        return CheckResult(
            "unknown_tickers", False,
            f"ticker-like tokens not in holdings or articles: {unknown}", severity="warn",
        )
    return CheckResult("unknown_tickers", True, severity="warn")


def run_structural_checks(
    brief: str, portfolio: dict, articles: list[dict], stop_reason: str | None = None
) -> list[CheckResult]:
    holdings = get_holdings(portfolio)
    sections = split_sections(brief)
    return [
        check_sections_present(brief),
        check_holdings_covered(sections, holdings),
        check_signal_tags(sections, holdings),
        check_disclaimer(sections),
        check_no_definitive_advice(brief),
        check_not_truncated(stop_reason),
        check_unknown_tickers(sections, holdings, articles),
    ]

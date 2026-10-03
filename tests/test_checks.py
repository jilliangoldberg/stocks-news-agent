import json
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
if "anthropic" not in sys.modules:
    sys.modules["anthropic"] = types.SimpleNamespace(Anthropic=object)

from evals.checks import run_structural_checks
from evals.judge import parse_grounding

PORTFOLIO = {
    "positions": [
        {"ticker": "AAPL", "allocation_pct": 50.0},
        {"ticker": "NVDA", "allocation_pct": 50.0},
    ],
    "themes": ["AI"],
    "risk_level": "medium",
}

ARTICLES = [
    {"title": "Nvidia beats estimates", "source": "X", "published_at": "", "summary": "NVDA revenue rose; AMD lagged.", "score": 5},
]

GOOD_BRIEF = """## 1. Top stories
- Nvidia beat estimates.

## 2. Market impact
Rates outlook is uncertain.

## 3. Portfolio impact
- **AAPL** — No direct catalyst today. **[Hold]**
- **NVDA** — Earnings beat may support sentiment, unlike AMD. **[Watch]**

## 4. Opportunities & risks
- AI demand looks durable.

## 5. Suggested actions
- Keep NVDA on the watchlist.

*These are probabilistic insights, not trading recommendations.*
"""


def results(brief, stop_reason="end_turn"):
    return {c.name: c for c in run_structural_checks(brief, PORTFOLIO, ARTICLES, stop_reason)}


def test_good_brief_passes_every_check():
    failed = [c for c in results(GOOD_BRIEF).values() if not c.passed]
    assert failed == []


def test_missing_section_fails():
    brief = GOOD_BRIEF.replace("## 4. Opportunities & risks\n- AI demand looks durable.\n\n", "")
    assert not results(brief)["sections_present"].passed


def test_section_heading_case_and_bold_are_tolerated():
    brief = GOOD_BRIEF.replace("## 1. Top stories", "## 1. **Top Stories**")
    assert results(brief)["sections_present"].passed


def test_missing_holding_fails():
    brief = GOOD_BRIEF.replace("- **AAPL** — No direct catalyst today. **[Hold]**\n", "")
    result = results(brief)["holdings_covered"]
    assert not result.passed
    assert "AAPL" in result.detail


def test_missing_tag_fails():
    brief = GOOD_BRIEF.replace(" **[Hold]**", "")
    assert not results(brief)["signal_tags_valid"].passed


def test_invalid_tag_fails():
    brief = GOOD_BRIEF.replace("[Hold]", "[Buy]")
    assert not results(brief)["signal_tags_valid"].passed


def test_holding_mentioned_in_another_line_uses_its_own_line():
    # NVDA appears in the AAPL line, but the NVDA line itself is what gets checked.
    brief = GOOD_BRIEF.replace("No direct catalyst today.", "Less exposed than NVDA.")
    assert results(brief)["signal_tags_valid"].passed


def test_missing_disclaimer_fails():
    brief = GOOD_BRIEF.replace("*These are probabilistic insights, not trading recommendations.*", "")
    assert not results(brief)["disclaimer_present"].passed


def test_definitive_advice_fails():
    brief = GOOD_BRIEF.replace("Keep NVDA on the watchlist.", "You should buy NVDA now.")
    assert not results(brief)["no_definitive_advice"].passed


def test_truncation_fails():
    assert not results(GOOD_BRIEF, stop_reason="max_tokens")["not_truncated"].passed


def test_unknown_ticker_is_a_warning():
    brief = GOOD_BRIEF.replace("Keep NVDA on the watchlist.", "Consider rotating into MSFT.")
    result = results(brief)["unknown_tickers"]
    assert not result.passed
    assert result.severity == "warn"
    assert "MSFT" in result.detail


def test_parse_grounding_reads_json_output():
    claims = [
        {"section": 1, "claim": "Nvidia beat estimates", "verdict": "supported", "article_ids": [1], "explanation": "Article 1."},
        {"section": 2, "claim": "CPI rose 0.4%", "verdict": "unsupported", "article_ids": [], "explanation": "Not in articles."},
        {"section": 4, "claim": "VOO tracks the S&P 500", "verdict": "general_knowledge", "article_ids": [], "explanation": "Stable fact."},
        {"section": 4, "claim": "junk", "verdict": "maybe", "article_ids": [], "explanation": "Invalid verdict dropped."},
    ]
    response = types.SimpleNamespace(
        stop_reason="end_turn",
        content=[
            types.SimpleNamespace(type="thinking", thinking=""),
            types.SimpleNamespace(type="text", text=json.dumps({"claims": claims})),
        ],
    )

    result = parse_grounding(response)

    assert result.n_claims == 3
    assert result.supported_rate == 2 / 3
    assert [c["claim"] for c in result.flagged()] == ["CPI rose 0.4%"]


def test_signal_tag_inside_bold_is_accepted():
    brief = GOOD_BRIEF.replace("**[Hold]**", "[**Hold**]")
    assert results(brief)["signal_tags_valid"].passed

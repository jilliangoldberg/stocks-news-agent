"""
Grounding judge: does every factual claim in the brief trace back to the input articles?
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import anthropic

from agent import ANTHROPIC_API_KEY, format_positions

DEFAULT_JUDGE_MODEL = "claude-opus-5-5"
VERDICTS = ["supported", "general_knowledge", "unsupported", "contradicted"]
ACCEPTABLE = {"supported", "general_knowledge"}

GROUNDING_SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "section": {"type": "integer", "description": "Brief section number (1, 2 or 4)."},
                    "claim": {"type": "string", "description": "The factual claim, quoted or closely paraphrased."},
                    "verdict": {"type": "string", "enum": VERDICTS},
                    "article_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Numbers of the articles that support or contradict the claim.",
                    },
                    "explanation": {"type": "string", "description": "One sentence on why."},
                },
                "required": ["section", "claim", "verdict", "article_ids", "explanation"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["claims"],
    "additionalProperties": False,
}

JUDGE_SYSTEM = (
    "You are a meticulous fact-checker for a financial news brief. "
    "You judge only whether claims are backed by the provided articles, not whether they are true in the world."
)


@dataclass
class GroundingResult:
    claims: list[dict] = field(default_factory=list)

    @property
    def n_claims(self) -> int:
        return len(self.claims)

    @property
    def supported_rate(self) -> float | None:
        """Share of claims backed by the articles, the portfolio, or stable general knowledge."""
        if not self.claims:
            return None
        return sum(c["verdict"] in ACCEPTABLE for c in self.claims) / len(self.claims)

    def flagged(self) -> list[dict]:
        return [c for c in self.claims if c["verdict"] not in ACCEPTABLE]

    def to_dict(self) -> dict:
        return {
            "n_claims": self.n_claims,
            "supported_rate": self.supported_rate,
            "flagged": self.flagged(),
            "claims": self.claims,
        }


def format_articles(articles: list[dict]) -> str:
    """Number articles the same way build_prompt does, with the same summary truncation."""
    return "\n".join(
        f"{i}. [{a['source']}] {a['title']}\n   Published: {a['published_at']}\n   Summary: {a['summary'][:300]}\n"
        for i, a in enumerate(articles, 1)
    )


def build_judge_prompt(brief: str, articles: list[dict], portfolio: dict) -> str:
    return f"""Below are the portfolio and news articles a model was given, followed by the daily brief it wrote.

PORTFOLIO (holdings & allocations %):
{format_positions(portfolio)}

ARTICLES:
{format_articles(articles)}

BRIEF:
{brief}

Extract every factual claim from sections 1 (Top stories), 2 (Market impact) and 4 (Opportunities & risks).
A factual claim is a statement about events, numbers, dates, companies, people or what someone said or did.
Skip pure opinion, hedged forecasts ("could pressure multiples") and generic framing.

Label each claim:
- supported: stated in, or directly implied by, one or more articles, or consistent with the portfolio data
- general_knowledge: not in the articles, but a stable, widely known fact rather than news (e.g. "VOO tracks the S&P 500")
- unsupported: not found in the articles (even if it might be true in the real world)
- contradicted: conflicts with what an article or the portfolio data says

Any claim about recent events, prices, data releases or what someone said or did is news: it is never general_knowledge.

Return every claim in the JSON format requested."""


def parse_grounding(response) -> GroundingResult:
    """Read the schema-constrained JSON out of a Messages API response."""
    if response.stop_reason in ("refusal", "max_tokens"):
        raise ValueError(f"judge stopped early: {response.stop_reason}")
    text = next((b.text for b in response.content if getattr(b, "type", None) == "text"), None)
    if text is None:
        raise ValueError("judge response had no text block")
    claims = json.loads(text).get("claims", [])
    return GroundingResult([c for c in claims if c.get("verdict") in VERDICTS])


def judge_grounding(brief: str, articles: list[dict], portfolio: dict, model: str = DEFAULT_JUDGE_MODEL) -> GroundingResult:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=model,
        max_tokens=16000,
        system=JUDGE_SYSTEM,
        output_config={
            "effort": "high",
            "format": {"type": "json_schema", "schema": GROUNDING_SCHEMA},
        },
        messages=[{"role": "user", "content": build_judge_prompt(brief, articles, portfolio)}],
    )
    return parse_grounding(response)

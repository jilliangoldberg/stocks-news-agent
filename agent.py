"""
AI Market Intelligence Agent — MVP
Fetches news, filters by portfolio relevance, generates a daily brief via LLM.
Output: console + local JSON/text file.
"""

import os
import json
import datetime
import requests
from dotenv import load_dotenv
import anthropic

load_dotenv()

# ── Configuration ─────────────────────────────────────────────────────────────

PORTFOLIO = {
    "holdings": ["AAPL", "NVDA", "TSLA", "VOO"],
    "themes": ["AI", "tech", "consumer"],
    "risk_level": "medium",
}

MACRO_KEYWORDS = [
    "inflation", "fed", "federal reserve", "interest rate", "cpi", "pce",
    "gdp", "recession", "jobs", "unemployment", "earnings", "fomc",
    "treasury", "yield", "monetary policy", "rate cut", "rate hike",
    "s&p", "nasdaq", "dow", "market", "stocks", "equities",
]

NEWS_API_KEY = os.getenv("NEWS_API_KEY")
NYT_API_KEY = os.getenv("NYT_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "./briefs")

TOP_N_ARTICLES = 12
NEWS_FETCH_COUNT = 20


# ── Step 1: News ingestion ────────────────────────────────────────────────────

def fetch_news_newsapi(query: str = "stock market finance economy", page_size: int = NEWS_FETCH_COUNT) -> list[dict]:
    """Fetch recent articles from NewsAPI."""
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": page_size,
        "apiKey": NEWS_API_KEY,
    }
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    articles = response.json().get("articles", [])
    print(f"      NewsAPI: {len(articles)} articles")
    return articles


def fetch_news_nyt(query: str = "stock market finance economy", page_size: int = NEWS_FETCH_COUNT) -> list[dict]:
    """Fetch recent articles from NYT Article Search API, normalized to NewsAPI format."""
    url = "https://api.nytimes.com/svc/search/v2/articlesearch.json"
    params = {
        "q": query,
        "sort": "newest",
        "api-key": NYT_API_KEY,
    }
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    docs = response.json().get("response", {}).get("docs", [])[:page_size]
    articles = [
        {
            "title": doc.get("headline", {}).get("main", ""),
            "description": doc.get("abstract") or doc.get("snippet") or "",
            "content": doc.get("lead_paragraph") or "",
            "url": doc.get("web_url", ""),
            "publishedAt": doc.get("pub_date", ""),
            "source": {"name": "The New York Times"},
        }
        for doc in docs
    ]
    print(f"      NYT:     {len(articles)} articles")
    return articles


def fetch_news(query: str = "stock market finance economy", page_size: int = NEWS_FETCH_COUNT) -> list[dict]:
    """Fetch and merge articles from NewsAPI and NYT."""
    newsapi_articles, nyt_articles = [], []

    if NEWS_API_KEY:
        newsapi_articles = fetch_news_newsapi(query, page_size)
    if NYT_API_KEY:
        nyt_articles = fetch_news_nyt(query, page_size)

    combined = newsapi_articles + nyt_articles
    print(f"[1/5] Fetched {len(combined)} total articles (NewsAPI + NYT)")
    return combined


# ── Step 2: Filtering & ranking ───────────────────────────────────────────────

def score_article(article: dict, portfolio: dict) -> float:
    """Score an article on keyword relevance, ticker mentions, and recency."""
    text = (
        (article.get("title") or "") + " " +
        (article.get("description") or "") + " " +
        (article.get("content") or "")
    ).lower()

    score = 0.0

    # Keyword relevance (macro/market terms)
    for kw in MACRO_KEYWORDS:
        if kw in text:
            score += 1.0

    # Portfolio ticker mentions (higher weight)
    for ticker in portfolio["holdings"]:
        if ticker.lower() in text:
            score += 3.0

    # Theme mentions
    for theme in portfolio["themes"]:
        if theme.lower() in text:
            score += 1.5

    # Recency boost: articles from last 12 hours get +2
    published = article.get("publishedAt", "")
    if published:
        try:
            pub_dt = datetime.datetime.fromisoformat(published.replace("Z", "+00:00"))
            age_hours = (datetime.datetime.now(datetime.timezone.utc) - pub_dt).total_seconds() / 3600
            if age_hours <= 12:
                score += 2.0
            elif age_hours <= 24:
                score += 1.0
        except ValueError:
            pass

    return round(score, 2)


def filter_and_rank(articles: list[dict], portfolio: dict, top_n: int = TOP_N_ARTICLES) -> list[dict]:
    """Score, deduplicate by title, and return top N articles."""
    seen_titles = set()
    scored = []

    for art in articles:
        title = art.get("title", "")
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)

        score = score_article(art, portfolio)
        if score > 0:
            scored.append({
                "title": title,
                "source": (art.get("source") or {}).get("name", "Unknown"),
                "url": art.get("url", ""),
                "published_at": art.get("publishedAt", ""),
                "summary": art.get("description") or art.get("content") or "",
                "score": score,
            })

    ranked = sorted(scored, key=lambda x: x["score"], reverse=True)[:top_n]
    print(f"[2/5] Filtered to {len(ranked)} relevant articles (from {len(articles)} fetched)")
    return ranked


# ── Step 3: Portfolio context injection ───────────────────────────────────────

def build_prompt(articles: list[dict], portfolio: dict) -> str:
    """Construct the LLM prompt with articles and portfolio context."""
    articles_text = ""
    for i, art in enumerate(articles, 1):
        articles_text += (
            f"{i}. [{art['source']}] {art['title']}\n"
            f"   Published: {art['published_at']}\n"
            f"   Summary: {art['summary'][:300]}\n"
            f"   Relevance score: {art['score']}\n\n"
        )

    prompt = f"""You are a market intelligence analyst generating a concise daily brief for a private investor.

PORTFOLIO CONTEXT (no sensitive data included):
- Holdings: {', '.join(portfolio['holdings'])}
- Investment themes: {', '.join(portfolio['themes'])}
- Risk level: {portfolio['risk_level']}

TODAY'S TOP NEWS ARTICLES (ranked by relevance):
{articles_text}

Generate a structured daily brief with exactly these five sections. Be concise, factual, and probabilistic — never definitive. Flag uncertainty where relevant. This is decision-support, not advice.

## 1. Top stories
Bullet-point summaries of the 4–5 most important articles. One sentence each.

## 2. Market impact
Short analysis of: (a) inflation/rates outlook, (b) sector trends, (c) overall risk sentiment. 2–3 sentences.

## 3. Portfolio impact
For each holding ({', '.join(portfolio['holdings'])}), one sentence on how today's news may affect it. Include a signal tag: [Watch] / [Hold] / [Caution].

## 4. Opportunities & risks
2–3 bullet points on emerging opportunities or downside risks visible in today's news.

## 5. Suggested actions
2–3 non-definitive watchlist/rebalancing/hedging ideas. End with: "These are probabilistic insights, not trading recommendations."
"""
    print("[3/5] Portfolio context injected into prompt")
    return prompt


# ── Step 4: LLM analysis ─────────────────────────────────────────────────────

def run_llm(prompt: str) -> str:
    """Call Claude to generate the structured brief."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    print("[4/5] Sending to Claude for analysis...")
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        system=(
            "You are a senior market intelligence analyst. "
            "You write clear, structured, probabilistic daily briefs. "
            "You never give definitive buy/sell advice. "
            "You flag uncertainty honestly."
        ),
        messages=[
            {"role": "user", "content": prompt},
        ],
    )
    return response.content[0].text


# ── Step 5: Save output ───────────────────────────────────────────────────────

def save_output(brief: str, articles: list[dict]) -> str:
    """Save brief as a .txt file and articles metadata as .json."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")

    # Save the brief
    brief_path = os.path.join(OUTPUT_DIR, f"brief_{date_str}.md")
    header = (
        f"# AI Market Intelligence Brief\n"
        f"**Generated:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}  \n"
        f"**Portfolio:** {', '.join(PORTFOLIO['holdings'])}\n\n"
        f"---\n\n"
    )
    with open(brief_path, "w") as f:
        f.write(header + brief)

    # Save article metadata
    meta_path = os.path.join(OUTPUT_DIR, f"articles_{date_str}.json")
    with open(meta_path, "w") as f:
        json.dump(articles, f, indent=2)

    print(f"[5/5] Brief saved to: {brief_path}")
    print(f"      Article metadata saved to: {meta_path}")
    return brief_path


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run_agent():
    print("\n" + "═" * 60)
    print("  AI MARKET INTELLIGENCE AGENT")
    print(f"  {datetime.datetime.now().strftime('%A, %B %-d %Y · %I:%M %p')}")
    print("═" * 60 + "\n")

    # Step 1 — Fetch
    raw_articles = fetch_news()

    # Step 2 — Filter & rank
    top_articles = filter_and_rank(raw_articles, PORTFOLIO)

    if not top_articles:
        print("No relevant articles found today. Exiting.")
        return

    # Step 3+4 — Prompt + LLM
    prompt = build_prompt(top_articles, PORTFOLIO)
    brief = run_llm(prompt)

    # Step 5 — Save
    save_output(brief, top_articles)

    # Print to console
    print("\n" + "─" * 60)
    print(brief)
    print("─" * 60 + "\n")


if __name__ == "__main__":
    run_agent()

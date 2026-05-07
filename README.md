# AI Market Intelligence Agent — MVP

A daily agent that fetches financial news, filters it against your portfolio context, and generates a structured brief using an LLM.

## Setup

```bash
# 1. Clone / copy files into a directory
cd market_agent

# 2. Create a virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up your API keys
cp .env.example .env
# Edit .env with your actual keys
```

## Get your API keys

- **NewsAPI**: https://newsapi.org/register (free tier: 100 req/day)
- **OpenAI**: https://platform.openai.com/api-keys

## Run manually

```bash
python agent.py
```

Briefs are saved to `./briefs/brief_YYYY-MM-DD.md` and article metadata to `./briefs/articles_YYYY-MM-DD.json`.

## Schedule at 8am daily (macOS / Linux)

```bash
# Open crontab
crontab -e

# Add this line (adjust paths to match your setup):
0 8 * * 1-5 /path/to/venv/bin/python /path/to/market_agent/agent.py >> /path/to/market_agent/cron.log 2>&1
```

This runs Monday–Friday at 8:00 AM. Change `1-5` to `*` for all 7 days.

## Customise your portfolio

You can use either:
- A single file: `portfolio.json`
- Multiple account files in a folder: `portfolio/*.json` (recommended for multiple accounts)

### Option A: Single account (`portfolio.json`)

```json
{
  "positions": [
    { "ticker": "AAPL", "allocation_pct": 25.0 },
    { "ticker": "NVDA", "allocation_pct": 25.0 },
    { "ticker": "TSLA", "allocation_pct": 20.0 },
    { "ticker": "VOO", "allocation_pct": 30.0 }
  ],
  "themes": ["AI", "tech", "consumer"],
  "risk_level": "medium"
}
```

The agent validates that all `allocation_pct` values add up to exactly `100%` (with tiny float tolerance).
No dollar amounts, balances, or account info are stored — only ticker symbols and percentages.

### Option B: Multiple accounts (`portfolio/`)

Create one JSON file per account (for example `portfolio/taxable.json`, `portfolio/retirement.json`):

```json
{
  "name": "taxable",
  "positions": [
    { "ticker": "AAPL", "allocation_pct": 35.0 },
    { "ticker": "NVDA", "allocation_pct": 25.0 },
    { "ticker": "VOO", "allocation_pct": 40.0 }
  ],
  "themes": ["AI", "tech", "core"],
  "risk_level": "medium"
}
```

Each account file is validated independently, and each account must total `100%`.
If `portfolio/` exists, the agent uses account files from that folder first.

## Output structure

Each brief covers:
1. Top stories (4–5 bullet summaries)
2. Market impact (rates, sectors, sentiment)
3. Portfolio impact (per-holding signal)
4. Opportunities & risks
5. Suggested actions (non-definitive)

## Next steps (after MVP works)

- [ ] Add Slack webhook delivery (`requests.post` to webhook URL)
- [ ] Add email delivery via `smtplib` or SendGrid
- [ ] Add Alpha Vantage for VIX / futures data
- [ ] Switch from cron to Prefect for observability
- [ ] Add a vector store for historical narrative tracking

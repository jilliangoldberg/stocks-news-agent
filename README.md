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

Briefs are saved to `./briefs/brief_YYYY-MM-DD.txt` and article metadata to `./briefs/articles_YYYY-MM-DD.json`.

## Schedule at 8am daily (macOS / Linux)

```bash
# Open crontab
crontab -e

# Add this line (adjust paths to match your setup):
0 8 * * 1-5 /path/to/venv/bin/python /path/to/market_agent/agent.py >> /path/to/market_agent/cron.log 2>&1
```

This runs Monday–Friday at 8:00 AM. Change `1-5` to `*` for all 7 days.

## Customise your portfolio

Edit the `PORTFOLIO` dict at the top of `agent.py`:

```python
PORTFOLIO = {
    "holdings": ["AAPL", "NVDA", "TSLA", "VOO"],  # your tickers
    "themes": ["AI", "tech", "consumer"],           # your investment themes
    "risk_level": "medium",                          # low / medium / high
}
```

No dollar amounts, balances, or account info — only tickers and themes.

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

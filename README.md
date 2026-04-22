# Daily Tech & AI News

Automated daily newsletter for technology and AI news.

Every day at **08:00 UTC** a GitHub Actions workflow:
1. Fetches the latest articles from curated tech & AI RSS feeds
2. Posts a formatted newsletter to the Slack **#daily-news** channel
3. Commits a dated Markdown archive file to this repository

## Archive structure

```
news/
└── YYYY/
    └── MM/
        └── YYYY-MM-DD.md
```

## Setup

### 1. Slack bot token

Create a Slack app with the `chat:write` scope and install it to your workspace.
Add the bot to your **#daily-news** channel.

### 2. GitHub secrets

| Secret | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude generation |
| `SLACK_BOT_TOKEN` | Slack bot token (`xoxb-…`) |
| `SLACK_CHANNEL` | Channel name or ID, e.g. `#daily-news` |

Go to **Settings → Secrets and variables → Actions → New repository secret** and add these values.

### 3. Enable Actions

Make sure GitHub Actions are enabled for the repository. The workflow runs automatically via cron.
You can also trigger it manually from **Actions → Daily Tech & AI Newsletter → Run workflow**.

## News sources

| Source | Category |
|---|---|
| TechCrunch | Tech |
| The Verge | Tech |
| Wired | Tech |
| Ars Technica | Tech |
| IEEE Spectrum | Tech |
| VentureBeat AI | AI |
| MIT Technology Review | AI |
| AI News | AI |

## Running locally

```bash
pip install -r requirements.txt
cp .env.example .env
# Fill ANTHROPIC_API_KEY and optional Slack values in .env
python scripts/fetch_news.py
```

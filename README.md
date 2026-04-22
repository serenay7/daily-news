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

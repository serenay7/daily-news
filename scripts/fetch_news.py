#!/usr/bin/env python3
"""
Daily Tech & AI News Newsletter
Fetches from RSS feeds, posts to Slack, and saves a dated markdown archive file.

Required env vars:
  SLACK_BOT_TOKEN  - Slack bot token (xoxb-...)
  SLACK_CHANNEL    - Channel name or ID (default: #daily-news)
"""

import os
import re
import datetime
from pathlib import Path

import feedparser
import requests


NEWS_SOURCES = [
    {"name": "TechCrunch",            "url": "https://techcrunch.com/feed/",                       "category": "Tech"},
    {"name": "The Verge",             "url": "https://www.theverge.com/rss/index.xml",              "category": "Tech"},
    {"name": "Wired",                 "url": "https://www.wired.com/feed/rss",                      "category": "Tech"},
    {"name": "VentureBeat AI",        "url": "https://venturebeat.com/ai/feed/",                    "category": "AI"},
    {"name": "MIT Technology Review", "url": "https://www.technologyreview.com/feed/",              "category": "AI"},
    {"name": "AI News",               "url": "https://www.artificialintelligence-news.com/feed/",   "category": "AI"},
    {"name": "Ars Technica",          "url": "https://feeds.arstechnica.com/arstechnica/index",     "category": "Tech"},
    {"name": "IEEE Spectrum",         "url": "https://spectrum.ieee.org/feeds/feed.rss",            "category": "Tech"},
]

MAX_PER_SOURCE = 3
SUMMARY_MAX_LEN = 350


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def truncate(text: str, max_len: int) -> str:
    return text[:max_len].rsplit(" ", 1)[0] + "…" if len(text) > max_len else text


def fetch_articles() -> list[dict]:
    articles = []
    for source in NEWS_SOURCES:
        try:
            feed = feedparser.parse(source["url"])
            for entry in feed.entries[:MAX_PER_SOURCE]:
                raw_summary = entry.get("summary", entry.get("description", ""))
                summary = truncate(strip_html(raw_summary), SUMMARY_MAX_LEN)
                articles.append({
                    "title":    entry.get("title", "No title").strip(),
                    "link":     entry.get("link", ""),
                    "summary":  summary,
                    "source":   source["name"],
                    "category": source["category"],
                })
        except Exception as exc:
            print(f"[WARN] Could not fetch {source['name']}: {exc}")
    return articles


# ── Markdown ──────────────────────────────────────────────────────────────────

def build_markdown(articles: list[dict], date: datetime.datetime) -> str:
    lines = [
        f"# Daily Tech & AI News — {date.strftime('%B %d, %Y')}",
        "",
        f"> Generated {date.strftime('%Y-%m-%d at %H:%M UTC')} · {len(articles)} articles",
        "",
        "---",
        "",
    ]

    by_category: dict[str, list[dict]] = {}
    for art in articles:
        by_category.setdefault(art["category"], []).append(art)

    for category, items in by_category.items():
        lines += [f"## {category}", ""]
        for art in items:
            lines += [
                f"### [{art['title']}]({art['link']})",
                f"**Source:** {art['source']}",
                "",
                art["summary"],
                "",
                "---",
                "",
            ]

    return "\n".join(lines)


# ── Slack ─────────────────────────────────────────────────────────────────────

CATEGORY_EMOJI = {"AI": "🤖", "Tech": "💻"}


def build_slack_blocks(articles: list[dict], date: datetime.datetime) -> list[dict]:
    blocks: list[dict] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"📰 Daily Tech & AI News — {date.strftime('%B %d, %Y')}",
                "emoji": True,
            },
        },
        {
            "type": "context",
            "elements": [{
                "type": "mrkdwn",
                "text": (
                    f"Generated at *{date.strftime('%H:%M UTC')}* · "
                    f"{len(articles)} articles from {len(NEWS_SOURCES)} sources"
                ),
            }],
        },
        {"type": "divider"},
    ]

    by_category: dict[str, list[dict]] = {}
    for art in articles:
        by_category.setdefault(art["category"], []).append(art)

    for category, items in by_category.items():
        emoji = CATEGORY_EMOJI.get(category, "📌")
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*{emoji} {category}*"},
        })
        for art in items:
            snippet = truncate(art["summary"], 200)
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*<{art['link']}|{art['title']}>*\n"
                        f"_{art['source']}_ — {snippet}"
                    ),
                },
            })
        blocks.append({"type": "divider"})

    return blocks


def post_to_slack(blocks: list[dict], token: str, channel: str) -> None:
    resp = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "channel": channel,
            "text": "Daily Tech & AI News Newsletter",
            "blocks": blocks,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack error: {data.get('error')}")
    print(f"[OK] Posted to Slack channel {channel}")


# ── File archive ──────────────────────────────────────────────────────────────

def save_markdown(content: str, date: datetime.datetime) -> Path:
    path = Path("news") / date.strftime("%Y") / date.strftime("%m") / f"{date.strftime('%Y-%m-%d')}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"[OK] Saved → {path}")
    return path


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    date = datetime.datetime.utcnow()
    print(f"[INFO] Fetching news for {date.strftime('%Y-%m-%d')} …")

    articles = fetch_articles()
    print(f"[INFO] Fetched {len(articles)} articles")

    markdown = build_markdown(articles, date)
    save_markdown(markdown, date)

    slack_token = os.environ.get("SLACK_BOT_TOKEN")
    slack_channel = os.environ.get("SLACK_CHANNEL", "#daily-news")

    if slack_token:
        blocks = build_slack_blocks(articles, date)
        post_to_slack(blocks, slack_token, slack_channel)
    else:
        print("[WARN] SLACK_BOT_TOKEN not set — skipping Slack post")


if __name__ == "__main__":
    main()

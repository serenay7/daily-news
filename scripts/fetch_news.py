#!/usr/bin/env python3
"""
Daily Tech & AI News Newsletter
Fetches from RSS feeds, posts to Slack, and saves a dated markdown archive file.

Required env vars:
  GROQ_API_KEY    - Groq API key for newsletter generation
  SLACK_BOT_TOKEN - Slack bot token (xoxb-...)
  SLACK_CHANNEL   - Channel name or ID (default: #daily-news)
"""

import os
import re
import datetime
import json
from pathlib import Path

from groq import Groq
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


def load_dotenv() -> None:
    env_path = Path(".env")
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


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


def _claude_prompt_payload(articles: list[dict], date: datetime.datetime) -> str:
    payload = []
    for article in articles:
        payload.append({
            "title": article["title"],
            "source": article["source"],
            "category": article["category"],
            "summary": article["summary"],
            "link": article["link"],
        })

    return (
        "Create a concise daily newsletter in markdown from the JSON articles.\n"
        f"Date: {date.strftime('%Y-%m-%d')}\n"
        "Requirements:\n"
        "- Keep heading exactly: # Daily Tech & AI News — <Month DD, YYYY>\n"
        "- Include a short one paragraph intro.\n"
        "- Group by categories as ## AI and ## Tech.\n"
        "- For each article include:\n"
        "  - Title as markdown link\n"
        "  - Source line in bold\n"
        "  - A 1-2 sentence rewritten summary in plain english\n"
        "- Keep overall length readable for Slack.\n"
        "- Do not hallucinate facts that are not present in article summaries.\n\n"
        f"Articles JSON:\n{json.dumps(payload, ensure_ascii=False)}"
    )


def generate_markdown_with_groq(
    client: Groq,
    model: str,
    articles: list[dict],
    date: datetime.datetime,
) -> str:
    response = client.chat.completions.create(
        model=model,
        max_tokens=2200,
        temperature=0.2,
        messages=[{"role": "user", "content": _claude_prompt_payload(articles, date)}],
    )
    text = response.choices[0].message.content or ""
    text = text.strip()
    if not text:
        raise RuntimeError("Groq returned an empty newsletter response")
    return text


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
    load_dotenv()
    date = datetime.datetime.utcnow()
    print(f"[INFO] Fetching news for {date.strftime('%Y-%m-%d')} …")

    articles = fetch_articles()
    print(f"[INFO] Fetched {len(articles)} articles")

    groq_key = os.environ.get("GROQ_API_KEY")
    groq_model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

    markdown = build_markdown(articles, date)
    if groq_key:
        try:
            print(f"[INFO] Generating newsletter with Groq model {groq_model} …")
            client = Groq(api_key=groq_key)
            markdown = generate_markdown_with_groq(client, groq_model, articles, date)
            print("[OK] Generated newsletter with Groq")
        except Exception as exc:
            print(f"[WARN] Groq generation failed, using fallback formatter: {exc}")
    else:
        print("[WARN] GROQ_API_KEY not set — using fallback formatter")

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

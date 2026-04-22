#!/usr/bin/env python3
"""
Daily Tech & AI News Newsletter
Fetches from RSS feeds, posts to Slack, and saves a dated markdown archive file.

Required env vars:
  GROQ_API_KEY       - Groq API key for newsletter generation
  GMAIL_USER         - Gmail address to send from
  GMAIL_APP_PASSWORD - Gmail app password (not your account password)
  EMAIL_RECIPIENTS   - Comma-separated list of recipient emails
"""

import os
import re
import datetime
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from groq import Groq
import feedparser
import markdown as md
import requests


NEWS_SOURCES = [
    {"name": "TechCrunch",            "url": "https://techcrunch.com/feed/",                       "category": "Tech"},
    {"name": "The Verge",             "url": "https://www.theverge.com/rss/index.xml",              "category": "Tech"},
    {"name": "Wired",                 "url": "https://www.wired.com/feed/rss",                      "category": "Tech"},
    {"name": "VentureBeat AI",        "url": "https://venturebeat.com/ai/feed/",                    "category": "AI"},
    {"name": "MIT Technology Review", "url": "https://www.technologyreview.com/feed/",              "category": "AI"},
    {"name": "AI News",               "url": "https://www.artificialintelligence-news.com/feed/",   "category": "AI"},
    {"name": "Ars Technica",          "url": "https://feeds.arstechnica.com/arstechnica/index",     "category": "Tech"},
]

MAX_PER_SOURCE = 7
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


NEWSLETTER_EXAMPLE = """# Daily Tech & AI News — April 21, 2026

> Generated 2026-04-21 at 08:00 UTC · 10 articles

---

## 🤖 AI

### [OpenAI Surpasses $25B Annualized Revenue, Eyes IPO](https://example.com)

OpenAI has surpassed $25 billion in annualized revenue and is reportedly taking early steps toward a public listing, potentially as soon as late 2026. Rival Anthropic is approaching $19 billion in annualized revenue, reflecting explosive demand for foundation-model APIs.

---

## 💻 Tech

### [Workday's Sana Agents Ship with 300+ Prebuilt Skills](https://example.com)

Workday's co-founder-CEO unveiled the next wave of Sana, including a Self-Service Agent with 300+ prebuilt skills across pay, time, absence, and expense.

---

*Sources: [AI Flash Report](https://aiflashreport.com/) · [VentureBeat](https://venturebeat.com/)*"""


def _build_newsletter_prompt(articles: list[dict], date: datetime.datetime) -> str:
    payload = [
        {k: article[k] for k in ("title", "source", "category", "summary", "link")}
        for article in articles
    ]

    sources = " · ".join(
        f'[{a["source"]}]({a["link"]})' for a in articles
    )

    return f"""You are a tech newsletter editor. Produce output in EXACTLY this format — no deviations:

<example>
{NEWSLETTER_EXAMPLE}
</example>

Rules:
- Heading: # Daily Tech & AI News — <Month DD, YYYY>
- Second line: > Generated {date.strftime('%Y-%m-%d')} at 08:00 UTC · {{n}} articles
- Separate sections with ---
- Categories with emojis: ## 🤖 AI, ## 💻 Tech (only include categories that have articles)
- Each article: ### [Title](link) on its own line, then a blank line, then the summary
- NO **Source:** line — do not include the source name under the title
- Footer: *Sources: [Name](url) · [Name](url)*
- Do NOT add any text before or after the newsletter
- Do NOT hallucinate facts not present in the summaries

Title rules:
- Rewrite titles to be short, punchy, and eye-catching — max 8 words
- Drop filler words like "The role of", "introducing", "The most interesting"
- Lead with the key subject: company, product, or action

Summary rules:
- 2-3 sentences max
- Do NOT repeat or paraphrase the title in the first sentence — start with new information
- Be specific: name numbers, companies, products, or implications
- Write for a reader who already saw the headline

Selection rules:
- Pick the TOP 5 most newsworthy articles per category (max 5 AI, max 5 Tech)
- SKIP product reviews, buying guides, "best of" lists, recipes, lifestyle pieces, and opinion columns
- Prefer news about company announcements, product launches, research, funding, and industry developments

Date: {date.strftime('%B %d, %Y')}

Articles JSON:
{json.dumps(payload, ensure_ascii=False, indent=2)}

Sources footer (use only the sources whose articles you selected):
{sources}"""


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
        messages=[{"role": "user", "content": _build_newsletter_prompt(articles, date)}],
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


# ── Email ─────────────────────────────────────────────────────────────────────

def send_email(
    content: str,
    date: datetime.datetime,
    gmail_user: str,
    app_password: str,
    recipients: list[str],
) -> None:
    subject = f"Small Byte — {date.strftime('%B %d, %Y')}"

    html_body = f"""
    <html><body style="font-family:sans-serif;max-width:640px;margin:auto;padding:24px;color:#222;">
    {md.markdown(content)}
    </body></html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Small Byte <{gmail_user}>"
    msg["To"] = gmail_user
    msg["Bcc"] = ", ".join(recipients)

    msg.attach(MIMEText(content, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_user, app_password)
        server.sendmail(gmail_user, [gmail_user] + recipients, msg.as_string())

    print(f"[OK] Email sent to {len(recipients)} recipients")


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

    gmail_user = os.environ.get("GMAIL_USER")
    app_password = os.environ.get("GMAIL_APP_PASSWORD")
    recipients_raw = os.environ.get("EMAIL_RECIPIENTS", "")
    recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]

    if gmail_user and app_password and recipients:
        try:
            send_email(markdown, date, gmail_user, app_password, recipients)
        except Exception as exc:
            print(f"[WARN] Email sending failed: {exc}")
    else:
        print("[WARN] Email secrets not set — skipping email")


if __name__ == "__main__":
    main()

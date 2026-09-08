"""
Daily Environmental Innovation/Impact News Report
---------------------------------------------------
1. Pulls stories from a curated list of trusted RSS feeds (Reuters Sustainable
   Business, The Guardian Environment, Grist, InsideClimate News, Bloomberg
   Green, Canary Media, etc.)
2. Pulls stories from a broad Google News RSS search (no API key needed) for
   terms like "environmental innovation" and "climate breakthrough".
3. Deduplicates and hands the combined list to Claude, which ranks the top
   stories by real-world impact/innovation and writes a short digest.
4. Emails the digest via SMTP (works with Gmail app passwords, or any SMTP
   provider like SendGrid/Mailgun).

Run manually with:  python main.py
Scheduled daily via GitHub Actions (see .github/workflows/daily-report.yml)
"""

import os
import smtplib
import ssl
import time
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import quote_plus

import feedparser
import requests

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

# Trusted, curated RSS feeds. Add/remove freely.
TRUSTED_FEEDS = [
    "https://www.theguardian.com/environment/rss",
    "https://grist.org/feed/",
    "https://insideclimatenews.org/feed/",
    "https://canarymedia.com/articles.rss",
    "https://www.greenbiz.com/rss.xml",
    "https://e360.yale.edu/feed.xml",
    "https://www.sciencedaily.com/rss/earth_climate.xml",
]

# Broad search terms, pulled via Google News RSS (free, no API key required)
SEARCH_TERMS = [
    "environmental innovation",
    "climate technology breakthrough",
    "renewable energy milestone",
    "conservation success story",
]

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"

MAX_ARTICLES_TO_CLAUDE = 40      # cap how many raw articles we send to Claude
TOP_STORIES_COUNT = 7            # how many stories to feature in the email

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
ANTHROPIC_MODEL = "claude-sonnet-4-6"

EMAIL_FROM = os.environ["EMAIL_FROM"]
EMAIL_TO = os.environ["EMAIL_TO"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]  # app password, not your real password
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))


# ---------------------------------------------------------------------------
# STEP 1: COLLECT ARTICLES
# ---------------------------------------------------------------------------

def fetch_trusted_feeds():
    """Pull recent entries from the curated RSS feed list."""
    articles = []
    for url in TRUSTED_FEEDS:
        try:
            feed = feedparser.parse(url)
            source_name = feed.feed.get("title", url)
            for entry in feed.entries[:8]:  # recent entries per feed
                articles.append({
                    "title": entry.get("title", "").strip(),
                    "link": entry.get("link", "").strip(),
                    "summary": entry.get("summary", "")[:400],
                    "source": source_name,
                })
        except Exception as e:
            print(f"[warn] failed to fetch {url}: {e}")
    return articles


def fetch_search_results():
    """Pull recent entries from a broad Google News RSS search."""
    articles = []
    for term in SEARCH_TERMS:
        url = GOOGLE_NEWS_RSS.format(query=quote_plus(term))
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:10]:
                articles.append({
                    "title": entry.get("title", "").strip(),
                    "link": entry.get("link", "").strip(),
                    "summary": entry.get("summary", "")[:400],
                    "source": entry.get("source", {}).get("title", "Google News"),
                })
        except Exception as e:
            print(f"[warn] failed to search '{term}': {e}")
    return articles


def dedupe(articles):
    seen_titles = set()
    unique = []
    for a in articles:
        key = a["title"].lower().strip()
        if key and key not in seen_titles:
            seen_titles.add(key)
            unique.append(a)
    return unique


# ---------------------------------------------------------------------------
# STEP 2: RANK + SUMMARIZE WITH CLAUDE
# ---------------------------------------------------------------------------

def build_claude_prompt(articles):
    lines = []
    for i, a in enumerate(articles):
        lines.append(f"[{i}] TITLE: {a['title']}\nSOURCE: {a['source']}\nLINK: {a['link']}\nSNIPPET: {a['summary']}\n")
    article_block = "\n".join(lines)

    return f"""You are curating a daily email digest on environmental innovation and impact.

Below is a list of candidate articles (index, title, source, link, snippet).
Select the {TOP_STORIES_COUNT} stories that represent the most significant
real-world environmental innovation, impact, or progress today. Prioritize:
- Concrete breakthroughs (new tech, deployed solutions, measurable results)
- Meaningful policy or market shifts
- Avoid duplicate stories covering the same event
- Avoid vague opinion pieces with no news content

Return ONLY valid JSON (no markdown fences, no preamble), as a list of objects:
[
  {{"index": <int>, "headline": "<punchy 8-12 word headline>", "why_it_matters": "<2-3 sentence summary of the story and its significance>"}}
]

CANDIDATE ARTICLES:
{article_block}
"""


def call_claude(prompt):
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": ANTHROPIC_MODEL,
            "max_tokens": 2000,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    text_blocks = [b["text"] for b in data["content"] if b.get("type") == "text"]
    return "".join(text_blocks)


def parse_ranked_stories(raw_text, articles):
    import json
    cleaned = raw_text.strip().strip("`")
    if cleaned.lower().startswith("json"):
        cleaned = cleaned[4:].strip()
    ranked = json.loads(cleaned)

    stories = []
    for item in ranked:
        idx = item["index"]
        if 0 <= idx < len(articles):
            stories.append({
                "headline": item["headline"],
                "why_it_matters": item["why_it_matters"],
                "link": articles[idx]["link"],
                "source": articles[idx]["source"],
            })
    return stories


# ---------------------------------------------------------------------------
# STEP 3: BUILD + SEND EMAIL
# ---------------------------------------------------------------------------

def build_email_html(stories):
    date_str = datetime.now(timezone.utc).strftime("%B %d, %Y")
    rows = ""
    for i, s in enumerate(stories, 1):
        rows += f"""
        <tr>
          <td style="padding:16px 0; border-bottom:1px solid #e5e7eb;">
            <div style="font-size:12px; color:#059669; font-weight:600; text-transform:uppercase; letter-spacing:0.05em;">{s['source']}</div>
            <div style="font-size:17px; font-weight:700; color:#111827; margin:6px 0;">
              {i}. <a href="{s['link']}" style="color:#111827; text-decoration:none;">{s['headline']}</a>
            </div>
            <div style="font-size:14px; color:#4b5563; line-height:1.5;">{s['why_it_matters']}</div>
            <a href="{s['link']}" style="font-size:13px; color:#059669; text-decoration:none;">Read full story →</a>
          </td>
        </tr>
        """

    return f"""
    <html>
    <body style="font-family:-apple-system,Segoe UI,Roboto,sans-serif; background:#f9fafb; margin:0; padding:24px;">
      <table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px; margin:0 auto; background:#ffffff; border-radius:12px; overflow:hidden;">
        <tr>
          <td style="background:#065f46; padding:24px; text-align:center;">
            <div style="color:#ffffff; font-size:20px; font-weight:700;">🌍 Environmental Impact Digest</div>
            <div style="color:#d1fae5; font-size:13px; margin-top:4px;">{date_str}</div>
          </td>
        </tr>
        <tr><td style="padding:0 24px;"><table width="100%">{rows}</table></td></tr>
        <tr>
          <td style="padding:20px 24px; text-align:center; font-size:12px; color:#9ca3af;">
            Curated daily from trusted sources + broad web search, ranked by Claude.
          </td>
        </tr>
      </table>
    </body>
    </html>
    """


def send_email(html_body):
    date_str = datetime.now(timezone.utc).strftime("%b %d, %Y")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🌍 Environmental Impact Digest — {date_str}"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg.attach(MIMEText(html_body, "html"))

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
        server.login(EMAIL_FROM, EMAIL_PASSWORD)
        server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    print("Fetching trusted feeds...")
    trusted = fetch_trusted_feeds()
    print(f"  -> {len(trusted)} articles")

    print("Fetching broad search results...")
    searched = fetch_search_results()
    print(f"  -> {len(searched)} articles")

    all_articles = dedupe(trusted + searched)[:MAX_ARTICLES_TO_CLAUDE]
    print(f"Total unique articles sent to Claude: {len(all_articles)}")

    if not all_articles:
        print("No articles found. Exiting without sending email.")
        return

    prompt = build_claude_prompt(all_articles)
    print("Asking Claude to rank + summarize...")
    raw = call_claude(prompt)
    stories = parse_ranked_stories(raw, all_articles)
    print(f"Claude selected {len(stories)} stories.")

    html = build_email_html(stories)
    print("Sending email...")
    send_email(html)
    print("Done!")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Crop Intelligence Monitor (v3, turmeric focus)
-----------------------------------------------
Runs topic-grouped Google News searches (last 7 days only) plus Google Alerts
RSS feeds, keeps only items whose headline is actually about turmeric/curcumin,
skips anything already seen, emails a digest grouped by topic, and rebuilds a
static dashboard.
"""

import os
import re
import json
import time
import html
import smtplib
import hashlib
import urllib.parse
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import requests
import feedparser

KEYWORDS_FILE = "keywords.txt"
ALERTS_FEEDS_FILE = "alerts_feeds.txt"
SEEN_FILE = "seen_ids.json"
DASHBOARD_FILE = "docs/index.html"
MAX_SEEN_ITEMS = 5000
RESULTS_PER_QUERY = 10
NEWS_WINDOW = "7d"  # Google News only returns articles from this window

GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
ALERT_EMAIL_TO = os.environ.get("ALERT_EMAIL_TO", GMAIL_ADDRESS)

# A headline must match this to be kept. This removes the off-topic hits
# (halal bakeries, nuclear plants, generic market reports, etc).
RELEVANT = re.compile(
    r"turmeric|curcumin|curcuma|haldi|lakadong|spices board|apeda|national turmeric board",
    re.IGNORECASE,
)


def clean_title(text):
    text = re.sub(r"<[^>]+>", "", text or "")
    return html.unescape(text).strip()


def load_queries(path):
    """Returns a list of (topic, query). Lines starting with ## set the topic."""
    if not os.path.exists(path):
        return []
    topic = "General"
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if line.startswith("##"):
                topic = line.lstrip("#").strip() or "General"
                continue
            if line.startswith("#"):
                continue
            out.append((topic, line))
    return out


def load_feed_urls(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        lines = [ln.strip() for ln in f.readlines()]
    return [ln for ln in lines if ln and not ln.startswith("#")]


def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_seen(seen):
    if len(seen) > MAX_SEEN_ITEMS:
        items = sorted(seen.items(), key=lambda kv: kv[1].get("first_seen", ""))
        seen = dict(items[-MAX_SEEN_ITEMS:])
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(seen, f, indent=2)


def make_id(*parts):
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def norm_title(title):
    base = title.rsplit(" - ", 1)[0]
    return re.sub(r"[^a-z0-9]+", " ", base.lower()).strip()


def search_news(topic, query):
    results = []
    q = urllib.parse.quote(f"{query} when:{NEWS_WINDOW}")
    url = f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:RESULTS_PER_QUERY]:
            results.append({
                "source": "News",
                "topic": topic,
                "keyword": query,
                "title": clean_title(entry.get("title", "")),
                "link": entry.get("link", ""),
            })
    except Exception as e:
        print(f"[news] error for '{query}': {e}")
    return results


def search_alert_feed(feed_url):
    results = []
    try:
        feed = feedparser.parse(feed_url)
        name = feed.feed.get("title", "Google Alert").replace("Google Alert - ", "")
        for entry in feed.entries[:15]:
            results.append({
                "source": "Google Alerts",
                "topic": "Google Alerts",
                "keyword": name,
                "title": clean_title(entry.get("title", "")),
                "link": entry.get("link", ""),
            })
    except Exception as e:
        print(f"[alerts] error for feed '{feed_url[:60]}...': {e}")
    return results


def collect_all(queries, feed_urls):
    all_results = []
    for topic, query in queries:
        all_results.extend(search_news(topic, query))
        time.sleep(1.0)
    for feed_url in feed_urls:
        all_results.extend(search_alert_feed(feed_url))
        time.sleep(0.5)
    return all_results


def filter_new(results, seen):
    new_items = []
    dropped = 0
    run_titles = set()
    now_iso = datetime.now(timezone.utc).isoformat()
    for r in results:
        if not RELEVANT.search(r["title"]):
            dropped += 1
            continue
        item_id = make_id(r["source"], r["link"])
        if item_id in seen:
            continue
        nt = norm_title(r["title"])
        if nt in run_titles:
            continue
        run_titles.add(nt)
        seen[item_id] = {
            "title": r["title"],
            "link": r["link"],
            "source": r["source"],
            "topic": r["topic"],
            "keyword": r["keyword"],
            "first_seen": now_iso,
        }
        new_items.append(r)
    return new_items, seen, dropped


def send_email(new_items):
    if not (GMAIL_ADDRESS and GMAIL_APP_PASSWORD and ALERT_EMAIL_TO):
        print("Email not configured - skipping send.")
        return
    if not new_items:
        print("No new items - skipping email.")
        return

    by_topic = {}
    for item in new_items:
        by_topic.setdefault(item["topic"], []).append(item)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Turmeric Monitor: {len(new_items)} new item(s)"
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = ALERT_EMAIL_TO

    text_lines = []
    html_parts = ["<h2>Turmeric intelligence digest</h2>"]
    for topic, items in by_topic.items():
        text_lines.append(f"\n== {topic} ({len(items)}) ==")
        html_parts.append(f"<h3>{html.escape(topic)} ({len(items)})</h3><ul>")
        for it in items:
            text_lines.append(f"- {it['title']}\n  {it['link']}")
            html_parts.append(
                f"<li><a href=\"{html.escape(it['link'])}\">{html.escape(it['title'])}</a></li>"
            )
        html_parts.append("</ul>")

    msg.attach(MIMEText("\n".join(text_lines), "plain"))
    msg.attach(MIMEText("".join(html_parts), "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, [ALERT_EMAIL_TO], msg.as_string())
    print(f"Email sent to {ALERT_EMAIL_TO} with {len(new_items)} item(s).")


def build_dashboard(seen):
    os.makedirs(os.path.dirname(DASHBOARD_FILE), exist_ok=True)
    items = sorted(seen.items(), key=lambda kv: kv[1].get("first_seen", ""), reverse=True)[:300]

    rows = []
    for _id, it in items:
        label = it.get("topic") or it.get("keyword", "")
        title = html.escape(clean_title(it.get("title", "")))
        link = html.escape(it.get("link", ""))
        rows.append(
            f"<tr><td>{it.get('first_seen', '')[:16].replace('T', ' ')}</td>"
            f"<td>{html.escape(it.get('source', ''))}</td>"
            f"<td>{html.escape(label)}</td>"
            f"<td><a href=\"{link}\" target=\"_blank\">{title}</a></td></tr>"
        )

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Turmeric Intelligence Monitor</title>
<style>
  body {{ font-family: -apple-system, Arial, sans-serif; margin: 1rem; background: #fafafa; color: #222; }}
  h1 {{ font-size: 1.3rem; }}
  table {{ border-collapse: collapse; width: 100%; background: white; }}
  th, td {{ border: 1px solid #ddd; padding: 6px 8px; font-size: 0.85rem; text-align: left; }}
  th {{ background: #8a6d00; color: white; }}
  tr:nth-child(even) {{ background: #f6f3e8; }}
  .meta {{ color: #666; font-size: 0.85rem; margin-bottom: 1rem; }}
</style>
</head>
<body>
<h1>Turmeric Intelligence Monitor</h1>
<div class="meta">Last updated: {datetime.now(timezone.utc).isoformat(timespec='minutes')} UTC &middot; {len(seen)} items tracked</div>
<table>
<tr><th>First seen</th><th>Source</th><th>Topic</th><th>Headline</th></tr>
{''.join(rows)}
</table>
</body>
</html>"""

    with open(DASHBOARD_FILE, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"Dashboard written to {DASHBOARD_FILE} ({len(items)} rows shown).")


def main():
    queries = load_queries(KEYWORDS_FILE)
    feed_urls = load_feed_urls(ALERTS_FEEDS_FILE)
    print(f"Loaded {len(queries)} queries and {len(feed_urls)} Google Alerts feed(s).")
    seen = load_seen()

    results = collect_all(queries, feed_urls)
    print(f"Fetched {len(results)} raw results.")

    new_items, seen, dropped = filter_new(results, seen)
    print(f"Dropped {dropped} off-topic headline(s). {len(new_items)} new relevant item(s).")

    save_seen(seen)
    build_dashboard(seen)
    send_email(new_items)


if __name__ == "__main__":
    main()


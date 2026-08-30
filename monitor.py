#!/usr/bin/env python3
"""
Crop Intelligence Monitor
--------------------------
Searches News (Google News RSS), Reddit, YouTube, and Google Alerts (RSS) for
new mentions of medicinal/aromatic/nutraceutical crops, deduplicates against
previously seen items, emails a digest of anything new, and regenerates a
static dashboard.
"""

import os
import json
import time
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
REQUEST_TIMEOUT = 15

GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
ALERT_EMAIL_TO = os.environ.get("ALERT_EMAIL_TO", GMAIL_ADDRESS)
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")


def load_lines(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        lines = [ln.strip() for ln in f.readlines()]
    return [ln for ln in lines if ln and not ln.startswith("#")]


def load_keywords():
    return load_lines(KEYWORDS_FILE)


def load_alert_feeds():
    return load_lines(ALERTS_FEEDS_FILE)


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


def search_news(keyword):
    results = []
    q = urllib.parse.quote(keyword)
    url = f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:8]:
            results.append({
                "source": "News",
                "keyword": keyword,
                "title": entry.get("title", "").strip(),
                "link": entry.get("link", ""),
                "published": entry.get("published", ""),
            })
    except Exception as e:
        print(f"[news] error for '{keyword}': {e}")
    return results


def search_reddit(keyword):
    results = []
    q = urllib.parse.quote(keyword)
    url = f"https://www.reddit.com/search.json?q={q}&sort=new&limit=8"
    headers = {"User-Agent": "crop-monitor-script/1.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            print(f"[reddit] status {resp.status_code} for '{keyword}'")
            return results
        data = resp.json()
        for child in data.get("data", {}).get("children", []):
            post = child.get("data", {})
            results.append({
                "source": "Reddit",
                "keyword": keyword,
                "title": post.get("title", "").strip(),
                "link": f"https://www.reddit.com{post.get('permalink', '')}",
                "published": datetime.fromtimestamp(
                    post.get("created_utc", 0), tz=timezone.utc
                ).isoformat() if post.get("created_utc") else "",
            })
    except Exception as e:
        print(f"[reddit] error for '{keyword}': {e}")
    return results


def search_youtube(keyword):
    results = []
    if not YOUTUBE_API_KEY:
        return results
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": keyword,
        "type": "video",
        "order": "date",
        "maxResults": 6,
        "key": YOUTUBE_API_KEY,
    }
    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            print(f"[youtube] status {resp.status_code} for '{keyword}': {resp.text[:200]}")
            return results
        data = resp.json()
        for item in data.get("items", []):
            vid = item.get("id", {}).get("videoId")
            snippet = item.get("snippet", {})
            if not vid:
                continue
            results.append({
                "source": "YouTube",
                "keyword": keyword,
                "title": snippet.get("title", "").strip(),
                "link": f"https://www.youtube.com/watch?v={vid}",
                "published": snippet.get("publishedAt", ""),
            })
    except Exception as e:
        print(f"[youtube] error for '{keyword}': {e}")
    return results


def search_alert_feed(feed_url):
    results = []
    try:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries[:15]:
            results.append({
                "source": "Google Alerts",
                "keyword": feed.feed.get("title", "Google Alert").replace("Google Alert - ", ""),
                "title": entry.get("title", "").strip(),
                "link": entry.get("link", ""),
                "published": entry.get("published", ""),
            })
    except Exception as e:
        print(f"[alerts] error for feed '{feed_url[:60]}...': {e}")
    return results


def collect_all(keywords, alert_feeds):
    all_results = []
    for kw in keywords:
        all_results.extend(search_news(kw))
        time.sleep(0.5)
        all_results.extend(search_reddit(kw))
        time.sleep(0.5)
        all_results.extend(search_youtube(kw))
        time.sleep(0.5)

    for feed_url in alert_feeds:
        all_results.extend(search_alert_feed(feed_url))
        time.sleep(0.5)

    return all_results


def filter_new(results, seen):
    new_items = []
    now_iso = datetime.now(timezone.utc).isoformat()
    for r in results:
        item_id = make_id(r["source"], r["link"])
        if item_id not in seen:
            seen[item_id] = {
                "title": r["title"],
                "link": r["link"],
                "source": r["source"],
                "keyword": r["keyword"],
                "first_seen": now_iso,
            }
            new_items.append(r)
    return new_items, seen


def send_email(new_items):
    if not (GMAIL_ADDRESS and GMAIL_APP_PASSWORD and ALERT_EMAIL_TO):
        print("Email not configured — skipping send.")
        return
    if not new_items:
        print("No new items — skipping email.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Crop Monitor: {len(new_items)} new mention(s)"
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = ALERT_EMAIL_TO

    lines_text = []
    lines_html = ["<h2>New crop/plant mentions</h2><ul>"]
    by_source = {}
    for item in new_items:
        by_source.setdefault(item["source"], []).append(item)

    for source, items in by_source.items():
        lines_text.append(f"\n== {source} ==")
        lines_html.append(f"<h3>{source}</h3><ul>")
        for it in items:
            lines_text.append(f"- [{it['keyword']}] {it['title']}\n  {it['link']}")
            lines_html.append(
                f"<li><b>{it['keyword']}</b>: <a href='{it['link']}'>{it['title']}</a></li>"
            )
        lines_html.append("</ul>")
    lines_html.append("</ul>")

    text_body = "\n".join(lines_text)
    html_body = "".join(lines_html)

    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, [ALERT_EMAIL_TO], msg.as_string())
    print(f"Email sent to {ALERT_EMAIL_TO} with {len(new_items)} item(s).")


def build_dashboard(seen):
    os.makedirs(os.path.dirname(DASHBOARD_FILE), exist_ok=True)
    items = sorted(seen.items(), key=lambda kv: kv[1].get("first_seen", ""), reverse=True)[:300]

    rows = []
    for _id, it in items:
        rows.append(
            f"<tr><td>{it.get('first_seen','')[:16].replace('T',' ')}</td>"
            f"<td>{it.get('source','')}</td>"
            f"<td>{it.get('keyword','')}</td>"
            f"<td><a href='{it.get('link','')}' target='_blank'>{it.get('title','')}</a></td></tr>"
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Crop Intelligence Monitor</title>
<style>
  body {{ font-family: -apple-system, Arial, sans-serif; margin: 2rem; background: #fafafa; color: #222; }}
  h1 {{ font-size: 1.4rem; }}
  table {{ border-collapse: collapse; width: 100%; background: white; }}
  th, td {{ border: 1px solid #ddd; padding: 8px 10px; font-size: 0.9rem; text-align: left; }}
  th {{ background: #2f5233; color: white; }}
  tr:nth-child(even) {{ background: #f2f2f2; }}
  .meta {{ color: #666; font-size: 0.85rem; margin-bottom: 1rem; }}
</style>
</head>
<body>
<h1>Crop Intelligence Monitor</h1>
<div class="meta">Last updated: {datetime.now(timezone.utc).isoformat(timespec='minutes')} UTC &middot; {len(seen)} total items tracked</div>
<table>
<tr><th>First Seen</th><th>Source</th><th>Keyword</th><th>Title</th></tr>
{''.join(rows)}
</table>
</body>
</html>"""

    with open(DASHBOARD_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Dashboard written to {DASHBOARD_FILE} ({len(items)} rows shown).")


def main():
    keywords = load_keywords()
    alert_feeds = load_alert_feeds()
    print(f"Loaded {len(keywords)} keywords and {len(alert_feeds)} Google Alerts feed(s).")
    seen = load_seen()

    results = collect_all(keywords, alert_feeds)
    print(f"Fetched {len(results)} raw results across all sources.")

    new_items, seen = filter_new(results, seen)
    print(f"{len(new_items)} new item(s) found.")

    save_seen(seen)
    build_dashboard(seen)
    send_email(new_items)


if __name__ == "__main__":
    main()

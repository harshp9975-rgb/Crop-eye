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
ALERT_EMAIL_TO = os.environ.get("ALERT_EMAIL


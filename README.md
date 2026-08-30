# Crop Intelligence Monitor

Tracks new mentions of medicinal/aromatic/nutraceutical crops (turmeric, ashwagandha,
brahmi, stevia, etc.) across **News, Reddit, and YouTube**, emails you a digest of
anything new, and keeps a browsable dashboard — all for free, running on GitHub's
infrastructure (no server to pay for or maintain).

Runs 3x/day automatically once set up.

## What it covers (and what it honestly can't)

| Source | Coverage |
|---|---|
| News (Google News RSS) | ✅ Automatic, full |
| Reddit | ✅ Automatic, full |
| YouTube | ✅ Automatic, full (titles/descriptions) |
| Twitter/X | ❌ Not included — X's search API now requires a $100+/month paid tier |
| Instagram / TikTok | ❌ No public API for keyword search — see workaround below |

## Setup (about 15 minutes, one time)

### 1. Create a GitHub repo
- Go to github.com → New repository (can be private) → e.g. `crop-monitor`
- Upload all files in this folder to it (or `git init` + `git push` from here)

### 2. Get a Gmail App Password (for sending the digest)
1. Go to your Google Account → Security → turn on **2-Step Verification** (if not already on)
2. Go to https://myaccount.google.com/apppasswords
3. Create an app password (name it "crop-monitor") → copy the 16-character code

### 3. Get a free YouTube Data API key
1. Go to https://console.cloud.google.com/
2. Create a new project (any name)
3. Go to "APIs & Services" → "Library" → search **YouTube Data API v3** → Enable
4. Go to "Credentials" → "Create Credentials" → API Key → copy it
   (Free tier: 10,000 units/day — this script uses roughly 100 units/keyword/run, so ~23 keywords x 3 runs/day fits comfortably)

### 4. Add secrets to your GitHub repo
In your repo: Settings → Secrets and variables → Actions → New repository secret. Add:
- `GMAIL_ADDRESS` → harshh.p1569@gmail.com (or whichever Gmail sends the mail)
- `GMAIL_APP_PASSWORD` → the 16-character app password from step 2
- `ALERT_EMAIL_TO` → harshh.p1569@gmail.com
- `YOUTUBE_API_KEY` → the key from step 3

### 5. Enable GitHub Pages for the dashboard
Settings → Pages → Source: **Deploy from a branch** → Branch: `main`, folder: `/docs` → Save.
After the first workflow run, your dashboard will be live at:
`https://<your-username>.github.io/<repo-name>/`

### 6. Test it
Go to the "Actions" tab in your repo → "Crop Monitor" workflow → "Run workflow" (manual trigger).
Check that it completes without errors, then check your email and the dashboard URL.

That's it — it will now run automatically at ~08:30, 16:30, and 22:30 IST daily.

## Editing what it tracks
Open `keywords.txt` and add/remove crop names or phrases, one per line. Changes take
effect on the next scheduled run — no code changes needed.

## Instagram, TikTok, and X — manual/semi-automated workaround
These platforms don't offer free public search APIs, so full automation isn't possible.
Practical alternatives:
- **Google Alerts** (free): set up alerts for your keywords — it occasionally surfaces
  indexed Instagram/TikTok captions and X posts that get picked up by Google's crawler.
  Not comprehensive, but zero-effort.
- **Hashtag checks**: periodically search hashtags like #turmericfarming, #ashwagandha,
  #medicinalplants directly in-app — takes 5 minutes a week.
- **If your budget allows later**: X's API Basic tier (~$100/month) or a social
  listening tool (Brand24, Mention.com, ~$29-79/month) would close this gap fully.

## Troubleshooting
- **No email arriving**: check the Actions tab for a failed run and read the log —
  usually a wrong app password or 2FA not enabled.
- **YouTube results missing**: check your API key quota in Google Cloud Console.
- **Want it to run more often**: edit the `cron` lines in `.github/workflows/monitor.yml`
  (cron times are in UTC).

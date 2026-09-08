# 🌍 Daily Environmental Impact Digest

Automatically compiles the top environmental innovation/impact stories each
day (curated trusted sources + broad web search, ranked by Claude) and emails
you a digest every morning — runs on GitHub's free cloud scheduler, so it
works even if your laptop is off.

## How it works
1. `main.py` pulls recent articles from a curated RSS list (Guardian, Grist,
   InsideClimate News, Canary Media, etc.) plus a broad Google News RSS
   search for terms like "environmental innovation."
2. It sends the combined article list to Claude, which picks the top 7 by
   real-world impact and writes short "why it matters" summaries.
3. It emails you a formatted HTML digest.
4. GitHub Actions runs this on a daily cron schedule — no server needed.

## One-time setup (about 10 minutes)

### 1. Create a GitHub repo
- Go to github.com → New repository → name it e.g. `eco-news-bot` → Create.
- Upload these files (or use `git push` if you're comfortable with git):
  `main.py`, `requirements.txt`, `.github/workflows/daily-report.yml`, `README.md`

### 2. Get an Anthropic API key
- Go to console.anthropic.com → Get API keys → Create Key.
- Copy it — you'll paste it into GitHub secrets in step 4.
- Note: this uses pay-as-you-go API credits (separate from your claude.ai
  subscription). One run costs a fraction of a cent.

### 3. Set up a Gmail App Password (or your SMTP provider)
If using Gmail:
- Go to myaccount.google.com/security → turn on 2-Step Verification if not
  already on.
- Go to myaccount.google.com/apppasswords → create a new app password
  (name it "eco-news-bot") → copy the 16-character password.
- **Do not use your real Gmail password** — this app password is what goes
  into GitHub secrets.

(If you'd rather use Outlook, SendGrid, or another SMTP provider, just swap
`SMTP_HOST` / `SMTP_PORT` env vars accordingly — let me know and I'll adjust.)

### 4. Add secrets to your GitHub repo
In your repo: Settings → Secrets and variables → Actions → New repository
secret. Add these four:

| Secret name | Value |
|---|---|
| `ANTHROPIC_API_KEY` | your Anthropic API key |
| `EMAIL_FROM` | the Gmail address sending the digest |
| `EMAIL_TO` | the address you want to receive it at (can be the same) |
| `EMAIL_PASSWORD` | the 16-character app password from step 3 |

### 5. Test it
- Go to the Actions tab in your repo → "Daily Environmental Digest" →
  "Run workflow" → Run workflow (green button). This triggers it manually
  without waiting for the schedule.
- Check the run logs for errors, and check your inbox.

### 6. Let it run
Once it works, it'll fire automatically every day at 11:00 UTC (~7am US
Eastern). To change the time, edit the `cron` line in
`.github/workflows/daily-report.yml` — cron format is `minute hour * * *`
in UTC.

## Customizing
- **Sources**: edit `TRUSTED_FEEDS` in `main.py` to add/remove RSS feeds.
- **Search terms**: edit `SEARCH_TERMS` to change what the broad search
  looks for.
- **Number of stories**: change `TOP_STORIES_COUNT` in `main.py`.
- **Email design**: edit `build_email_html()` in `main.py`.

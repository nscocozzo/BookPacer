# BookPacer

A small web tool that keeps you on pace with your library books so you finish
them before they are due. Enter your current place in each book and BookPacer
tells you how many pages to read each night — with an optional daily Discord
webhook reminder.

## Features

- 📖 Track any number of library books: title, author, total pages, current
  page, and due date.
- 🎯 Automatic pacing: pages per night (rounded up) to finish exactly on the
  due date, with overdue and finished states.
- 🔔 **Discord reminders**: one webhook message per day with tonight's page
  goal for every book.
- 💾 Everything is stored locally in a single JSON file — no database needed.

## Setup

Requires Python 3.10+.

```bash
pip install -r requirements.txt
python -m bookpacer.app
```

Then open <http://127.0.0.1:5000>.

## Using BookPacer

1. **Add a book** with its title, total page count, your current page, and the
   library due date.
2. **Update your current page** in that book's row each day as you read —
   type the new page number and click *Update*.
3. **Paste your Discord webhook URL** in the settings section
   (Discord channel → *Edit Channel → Integrations → Webhooks → New Webhook*).
   Use *Send reminder now* to test it.

## Accessing BookPacer from your phone

Running `python -m bookpacer.app` only serves BookPacer on your own computer
(`127.0.0.1`), which isn't reachable from your phone unless it's hosted
somewhere else. If you're fine with it being reachable on the public
internet, host it on a small always-on service with persistent storage —
**[PythonAnywhere](https://www.pythonanywhere.com)** works well for this:
its free tier runs Flask apps directly (no code changes needed), keeps your
`data/bookpacer.json` on real persistent disk, and even includes one free
daily scheduled task, which is enough to run `python -m bookpacer.remind`.

> Netlify won't work for BookPacer as-is — it's built for static sites and
> stateless serverless functions, so `data/bookpacer.json` would be wiped on
> every deploy/cold start. Using it would mean replacing the JSON file with an
> external database, which is a rewrite rather than a hosting change.

Since the app will be reachable by anyone who finds the URL, set a shared
password so only you can add/update/delete books or change settings — see
**Protecting a public deployment** below.

### Updating from your phone without opening the browser

Instead of the web page, you can update a book's progress with a single curl
command — handy for an iOS Shortcut you run once a day:

```bash
curl -u bookpacer:yourpassword -X POST https://your-app-url/api/progress \
  --data-urlencode "title=The Midnight Library" \
  --data-urlencode "current_page=150"
```

It looks the book up by title (case-insensitive) and returns a short plain-text
reply, e.g. `The Midnight Library: 150/304 pages. Read 8 pages/night to stay
on pace.` — good for an iOS Shortcut's *Get Contents of URL* action (`POST`,
request body = form fields `title` / `current_page`, header
`Authorization: Basic <base64 of bookpacer:yourpassword>`) followed by
*Show Result*.

## Protecting a public deployment

Set `BOOKPACER_PASSWORD` to require HTTP Basic Auth on every request (any
username, that password). It's opt-in — leave it unset for local use and
the app stays open, exactly as before:

```bash
BOOKPACER_PASSWORD=yourpassword python -m bookpacer.app
```

## Daily Discord reminders

There are two ways to trigger it, depending on where BookPacer runs.

### Running locally or on a host you can schedule directly

```bash
python -m bookpacer.remind
```

The webhook URL comes from the saved settings, or from the
`DISCORD_WEBHOOK_URL` environment variable (handy for CI-based scheduling).

#### Example: cron (Linux/macOS)

```cron
0 18 * * *  cd /path/to/BookPacer && /usr/bin/python3 -m bookpacer.remind
```

### Hosted remotely without a scheduler (e.g. PythonAnywhere's free tier)

PythonAnywhere's free tier only gives you one *free* scheduled task, and
paid plans are needed for more — but you don't need one at all. The app
already exposes `POST /remind`, which sends tonight's reminder using
whatever data is currently live on the server. Have GitHub Actions call
that endpoint on a schedule instead of running `bookpacer.remind` itself,
so there's no need to duplicate or sync your books data into a secret:

```yaml
# .github/workflows/daily-reminder.yml
name: Daily reading reminder
on:
  schedule:
    - cron: "30 2 * * *"   # UTC — pick your evening
  workflow_dispatch:

jobs:
  remind:
    runs-on: ubuntu-latest
    env:
      BOOKPACER_URL: ${{ secrets.BOOKPACER_URL }}
      BOOKPACER_PASSWORD: ${{ secrets.BOOKPACER_PASSWORD }}
    steps:
      - name: Skip when reminder secrets are not configured
        if: ${{ env.BOOKPACER_URL == '' || env.BOOKPACER_PASSWORD == '' }}
        run: |
          echo "Skipping reminder: set both BOOKPACER_URL and BOOKPACER_PASSWORD repository secrets to enable this workflow."
      - name: Trigger remote reminder
        if: ${{ env.BOOKPACER_URL != '' && env.BOOKPACER_PASSWORD != '' }}
        run: |
          curl -fsS -u "bookpacer:$BOOKPACER_PASSWORD" -X POST "${BOOKPACER_URL%/}/remind"
```

Add two repository secrets (**Settings → Secrets and variables →
Actions**):

- `BOOKPACER_URL` — e.g. `https://yourusername.pythonanywhere.com`
- `BOOKPACER_PASSWORD` — the same value as your app's `BOOKPACER_PASSWORD`

This only works if the deployment has `BOOKPACER_PASSWORD` set (see
**Protecting a public deployment** above) — without it, anyone could hit
`/remind` and spam your Discord webhook.

If those two secrets are not configured yet, the workflow now exits cleanly
with a skip message instead of failing with an invalid `curl` URL.


## Configuration

| Environment variable  | Purpose                                             |
| --------------------- | --------------------------------------------------- |
| `BOOKPACER_DATA`      | Path to the JSON data file (default `data/bookpacer.json`) |
| `BOOKPACER_PASSWORD`  | If set, requires HTTP Basic Auth (any username) on every request |
| `DISCORD_WEBHOOK_URL` | Webhook URL override for `python -m bookpacer.remind`      |

## Development

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -q
```
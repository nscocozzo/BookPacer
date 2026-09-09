# BookPacer

A small web tool that keeps you on pace with your library books so you finish
them before they are due. Enter your current place in each book (or paste your
progress straight from [Fable](https://fable.co)), and BookPacer tells you how
many pages to read each night — with an optional daily Discord webhook
reminder.

## Features

- 📖 Track any number of library books: title, author, total pages, current
  page, and due date.
- 🎯 Automatic pacing: pages per night (rounded up) to finish exactly on the
  due date, with overdue and finished states.
- 📥 **Fable import**: paste your current reads from Fable (`Title by Author`,
  `45%`, `304 pages` — or the `Title: / Author: / Progress: / Pages:` format)
  and BookPacer converts your percent-read into a current page and works out
  how many pages are left. Re-importing later simply refreshes your progress.
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

1. **Add a book** with its total page count, your current page, and the
   library due date — or **import from Fable** by pasting your book details
   into the import box.
2. **Update your current page** as you read (or re-import from Fable).
3. **Paste your Discord webhook URL** in the settings section
   (Discord channel → *Edit Channel → Integrations → Webhooks → New Webhook*).
   Use *Send reminder now* to test it.

## Daily Discord reminders

Run the reminder once a day with any scheduler:

```bash
python -m bookpacer.remind
```

The webhook URL comes from the saved settings, or from the
`DISCORD_WEBHOOK_URL` environment variable (handy for CI-based scheduling).

### Example: cron (Linux/macOS)

```cron
0 18 * * *  cd /path/to/BookPacer && /usr/bin/python3 -m bookpacer.remind
```

### Example: GitHub Actions

Because `data/*.json` is gitignored, your books data does not travel with the
repo. Store the contents of your `data/bookpacer.json` in a repository secret
(e.g. `BOOKPACER_DATA_JSON`, in a **private** repo — it contains your webhook
URL) and write it out in a step:

```yaml
# .github/workflows/daily-reminder.yml
name: Daily reading reminder
on:
  schedule:
    - cron: "0 22 * * *"   # UTC — pick your evening
  workflow_dispatch:

jobs:
  remind:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - name: Restore books data
        run: |
          mkdir -p data
          printf '%s' "$BOOKPACER_DATA_JSON" > data/bookpacer.json
        env:
          BOOKPACER_DATA_JSON: ${{ secrets.BOOKPACER_DATA_JSON }}
      - run: python -m bookpacer.remind
        env:
          DISCORD_WEBHOOK_URL: ${{ secrets.DISCORD_WEBHOOK_URL }}
          BOOKPACER_DATA: data/bookpacer.json
```

## Configuration

| Environment variable  | Purpose                                             |
| --------------------- | --------------------------------------------------- |
| `BOOKPACER_DATA`      | Path to the JSON data file (default `data/bookpacer.json`) |
| `DISCORD_WEBHOOK_URL` | Webhook URL override for `python -m bookpacer.remind`      |

## Development

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -q
```
"""Send the daily BookPacer Discord reminder.

Run from a scheduler (cron, Task Scheduler, GitHub Actions, ...) once a day:

    python -m bookpacer.remind

The webhook URL is read from the saved settings, or from the
DISCORD_WEBHOOK_URL environment variable (useful for CI schedulers where
no web UI is running).
"""

from __future__ import annotations

import os
import sys

from .pacing import load_data, send_discord_reminder


def main() -> int:
    data = load_data()
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL") or data["settings"].get(
        "webhook_url", ""
    )
    if not webhook_url:
        print(
            "No Discord webhook configured. Set it in the web UI or via the "
            "DISCORD_WEBHOOK_URL environment variable.",
            file=sys.stderr,
        )
        return 1
    try:
        send_discord_reminder(webhook_url, data["books"])
    except (ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Reminder sent for {len(data['books'])} book(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

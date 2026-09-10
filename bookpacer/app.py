"""Flask web application for BookPacer."""

from __future__ import annotations

import os
import secrets
from datetime import date

from flask import Flask, Response, flash, redirect, render_template, request, url_for

from . import pacing


def create_app(data_path: str | None = None) -> Flask:
    app = Flask(__name__)
    # Only used to sign flash-message cookies; random per start unless set.
    app.secret_key = os.environ.get("BOOKPACER_SECRET_KEY") or os.urandom(24)
    app.config["BOOKPACER_DATA"] = data_path

    @app.before_request
    def require_auth():
        # Auth is opt-in: only enforced once BOOKPACER_PASSWORD is set, so
        # local/dev use (and the test suite) needs no credentials.
        password = os.environ.get("BOOKPACER_PASSWORD")
        if not password:
            return None
        auth = request.authorization
        if not auth or not secrets.compare_digest(auth.password, password):
            return Response(
                "Authentication required.",
                401,
                {"WWW-Authenticate": 'Basic realm="BookPacer"'},
            )
        return None

    def load() -> dict:
        return pacing.load_data(data_path)

    def save(data: dict) -> None:
        pacing.save_data(data, data_path)

    @app.route("/")
    def index():
        data = load()
        today = date.today()
        books = []
        for book in data["books"]:
            books.append(
                {
                    **book,
                    "status": pacing.reading_status(
                        book["current_page"],
                        book["total_pages"],
                        pacing.parse_date(book["due_date"]),
                        today,
                    ),
                }
            )
        return render_template(
            "index.html",
            books=books,
            webhook_url=data["settings"].get("webhook_url", ""),
            today=today.isoformat(),
        )

    @app.route("/books", methods=["POST"])
    def add_book():
        try:
            book = pacing.normalize_book(request.form.to_dict())
        except (KeyError, ValueError, TypeError):
            flash(
                "Invalid book details — a title and a due date (YYYY-MM-DD) "
                "are required.",
                "error",
            )
            return redirect(url_for("index"))
        data = load()
        pacing.upsert_book(data, book)
        save(data)
        flash(f"Saved “{book['title']}”.", "success")
        return redirect(url_for("index"))

    @app.route("/books/<int:book_id>/progress", methods=["POST"])
    def update_progress(book_id: int):
        data = load()
        if not 0 <= book_id < len(data["books"]):
            flash("Book not found.", "error")
            return redirect(url_for("index"))
        try:
            page = int(request.form.get("current_page", ""))
        except ValueError:
            flash("Current page must be a number.", "error")
            return redirect(url_for("index"))
        book = data["books"][book_id]
        book["current_page"] = max(0, min(page, book["total_pages"] or page))
        save(data)
        flash(f"Updated progress for “{book['title']}”.", "success")
        return redirect(url_for("index"))

    @app.route("/books/<int:book_id>/delete", methods=["POST"])
    def delete_book(book_id: int):
        data = load()
        if 0 <= book_id < len(data["books"]):
            removed = data["books"].pop(book_id)
            save(data)
            flash(f"Removed “{removed['title']}”.", "success")
        return redirect(url_for("index"))

    @app.route("/api/progress", methods=["POST"])
    def api_update_progress():
        """Plain-text progress update for curl / iOS Shortcuts.

        Looks a book up by title (case-insensitive) instead of list index,
        since an index isn't a stable target for a saved Shortcut.
        """
        title = (request.form.get("title") or "").strip()
        if not title:
            return Response("title is required\n", 400, mimetype="text/plain")
        try:
            page = int(request.form.get("current_page", ""))
        except ValueError:
            return Response(
                "current_page must be a number\n", 400, mimetype="text/plain"
            )
        data = load()
        book = next(
            (b for b in data["books"] if b["title"].lower() == title.lower()),
            None,
        )
        if book is None:
            return Response(
                f"No book found matching {title!r}.\n", 404, mimetype="text/plain"
            )
        book["current_page"] = max(0, min(page, book["total_pages"] or page))
        save(data)
        status = pacing.reading_status(
            book["current_page"],
            book["total_pages"],
            pacing.parse_date(book["due_date"]),
            date.today(),
        )
        if status["is_finished"]:
            message = f"{book['title']}: finished!\n"
        elif status["is_overdue"]:
            message = f"{book['title']}: overdue, {status['pages_left']} pages left.\n"
        else:
            message = (
                f"{book['title']}: {book['current_page']}/{book['total_pages']} pages. "
                f"Read {status['pages_per_day']} pages/night to stay on pace.\n"
            )
        return Response(message, 200, mimetype="text/plain")

    @app.route("/settings", methods=["POST"])
    def save_settings():
        data = load()
        data["settings"]["webhook_url"] = request.form.get("webhook_url", "").strip()
        save(data)
        flash("Discord webhook URL saved.", "success")
        return redirect(url_for("index"))

    @app.route("/remind", methods=["POST"])
    def remind_now():
        data = load()
        webhook_url = data["settings"].get("webhook_url", "")
        try:
            pacing.send_discord_reminder(webhook_url, data["books"])
        except (ValueError, RuntimeError) as exc:
            flash(str(exc), "error")
            return redirect(url_for("index"))
        flash("Discord reminder sent!", "success")
        return redirect(url_for("index"))

    return app


app = create_app()

if __name__ == "__main__":
    # Never enable the debugger here; set FLASK_DEBUG=1 explicitly if needed.
    app.run(host="127.0.0.1", port=5000)

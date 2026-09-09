"""Flask web application for BookPacer."""

from __future__ import annotations

import os
from datetime import date

from flask import Flask, flash, redirect, render_template, request, url_for

from . import pacing


def create_app(data_path: str | None = None) -> Flask:
    app = Flask(__name__)
    # Only used to sign flash-message cookies; random per start unless set.
    app.secret_key = os.environ.get("BOOKPACER_SECRET_KEY") or os.urandom(24)
    app.config["BOOKPACER_DATA"] = data_path

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

    @app.route("/import/fable", methods=["POST"])
    def import_fable():
        fable_text = request.form.get("fable_text", "")
        due_date = request.form.get("due_date") or None
        data = load()
        try:
            imported = pacing.import_fable_text(data, fable_text, due_date)
        except (ValueError, TypeError) as exc:
            flash(f"Could not import Fable data: {exc}", "error")
            return redirect(url_for("index"))
        if not imported:
            flash(
                "No books were recognised. Paste lines like "
                "“Title by Author”, “45%”, “304 pages” — or provide a due date.",
                "error",
            )
            return redirect(url_for("index"))
        save(data)
        titles = ", ".join(b["title"] for b in imported)
        flash(f"Imported {len(imported)} book(s) from Fable: {titles}.", "success")
        return redirect(url_for("index"))

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

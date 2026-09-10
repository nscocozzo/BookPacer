"""Tests for the BookPacer Fable sync CLI."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bookpacer import fable_sync


class FableSyncCliTests(unittest.TestCase):
    def test_imports_from_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "fable.txt")
            data_path = os.path.join(tmp, "bookpacer.json")
            with open(input_path, "w", encoding="utf-8") as fh:
                fh.write("Dune by Frank Herbert\n10%\n896 pages\n")

            rc = fable_sync.main(
                [
                    "--from-file",
                    input_path,
                    "--due-date",
                    "2026-09-30",
                    "--data-path",
                    data_path,
                ]
            )

            self.assertEqual(rc, 0)
            with open(data_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            self.assertEqual(len(data["books"]), 1)
            self.assertEqual(data["books"][0]["title"], "Dune")
            self.assertEqual(data["books"][0]["current_page"], 90)

    def test_returns_error_when_no_due_date_for_new_books(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "fable.txt")
            data_path = os.path.join(tmp, "bookpacer.json")
            with open(input_path, "w", encoding="utf-8") as fh:
                fh.write("Dune by Frank Herbert\n10%\n896 pages\n")

            rc = fable_sync.main(
                [
                    "--from-file",
                    input_path,
                    "--data-path",
                    data_path,
                ]
            )
            self.assertEqual(rc, 2)
            self.assertFalse(os.path.exists(data_path))


if __name__ == "__main__":
    unittest.main()
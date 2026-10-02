#!/usr/bin/env python3
"""Regression tests for the csv_cleaner.py public command-line interface.

Run from the repository root:

    python -m unittest discover

Coverage:
  * complex quoted fields (commas, embedded newlines, doubled quotes) keep
    their meaning while trim only changes the targeted cells, for both BOM
    and non-BOM UTF-8 input;
  * structural errors are located by CSV record number: a newline inside a
    quoted field must not turn the number into a physical line number.

Only the Python standard library is used. Every test builds its own input
inside a fresh temporary directory and removes it afterwards, so the tests
need no sample files from outside the repository and produce identical
results on repeated runs.
"""

import csv
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CLEANER = Path(__file__).resolve().parent / "csv_cleaner.py"

HEADER = ["name", "note"]
SUCCESS_ROWS = [
    [" Alice ", "x,y"],
    ["张 三", "第一行\n第二行"],
    ["   ", '他说"好"'],
]
EXPECTED_CLEANED_ROWS = [
    ["Alice", "x,y"],
    ["张 三", "第一行\n第二行"],
    ["", '他说"好"'],
]
BOM = b"\xef\xbb\xbf"


def encode_csv(rows, bom=False):
    """Serialize logical rows to CSV bytes; quoting is the writer's choice."""
    buffer = io.StringIO()
    csv.writer(buffer).writerows(rows)
    data = buffer.getvalue().encode("utf-8")
    return BOM + data if bom else data


def parse_csv(data):
    """Parse CSV bytes back into logical rows, tolerating an optional BOM."""
    text = data.decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text)))


class CsvCleanerCliTest(unittest.TestCase):
    def _run_cleaner(self, tmpdir, raw_input):
        in_path = Path(tmpdir) / "input.csv"
        out_path = Path(tmpdir) / "cleaned.csv"
        in_path.write_bytes(raw_input)
        proc = subprocess.run(
            [
                sys.executable,
                str(CLEANER),
                "--input",
                str(in_path),
                "--output",
                str(out_path),
                "--column",
                "name",
                "--rule",
                "trim",
            ],
            capture_output=True,
        )
        return proc, in_path, out_path

    def _assert_success(self, bom):
        raw_input = encode_csv([HEADER] + SUCCESS_ROWS, bom=bom)
        with tempfile.TemporaryDirectory() as tmpdir:
            proc, in_path, out_path = self._run_cleaner(tmpdir, raw_input)

            self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8"))
            self.assertEqual(proc.stderr, b"")

            stdout = proc.stdout.decode("utf-8")
            self.assertEqual(len(stdout.strip().splitlines()), 1)
            self.assertEqual(
                json.loads(stdout), {"rows": 3, "changed_cells": 2}
            )

            # The output is a brand-new file encoded as UTF-8 without BOM.
            self.assertTrue(out_path.exists())
            raw_output = out_path.read_bytes()
            self.assertFalse(raw_output.startswith(BOM))
            raw_output.decode("utf-8")  # raises if the bytes are not UTF-8

            # Fixture sanity: the input really carries the tricky contents.
            self.assertEqual(parse_csv(raw_input), [HEADER] + SUCCESS_ROWS)

            # Semantic comparison: quoting style and line endings are free to
            # differ between equivalent CSV serializations.
            self.assertEqual(
                parse_csv(raw_output), [HEADER] + EXPECTED_CLEANED_ROWS
            )

            # The input is opened read-only and must be byte-for-byte intact.
            self.assertEqual(in_path.read_bytes(), raw_input)

    def test_success_without_bom(self):
        self._assert_success(bom=False)

    def test_success_with_bom(self):
        self._assert_success(bom=True)

    def test_structural_error_uses_record_number(self):
        # The embedded newline makes "Bad" physical line 4, but it is CSV
        # record 3 (the header counts as record 1).
        bad_rows = [
            HEADER,
            ["张 三", "第一行\n第二行"],
            ["Bad"],
        ]
        raw_input = encode_csv(bad_rows)
        with tempfile.TemporaryDirectory() as tmpdir:
            proc, in_path, out_path = self._run_cleaner(tmpdir, raw_input)

            self.assertEqual(proc.returncode, 2)
            self.assertEqual(proc.stdout, b"")

            stderr = proc.stderr.decode("utf-8")
            self.assertTrue(stderr.startswith("error:"))
            self.assertIn("record 3", stderr)
            self.assertIn("1 field", stderr)
            self.assertIn("expected 2", stderr)
            self.assertNotIn("record 4", stderr)

            self.assertFalse(out_path.exists())
            self.assertEqual(in_path.read_bytes(), raw_input)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Regression tests for the csv_cleaner.py command-line entry point.

Run from the project root:

    python -m unittest discover

The tests exercise only the documented public CLI: quoted fields containing
commas, newlines and double quotes must survive a trim run unchanged, and a
structural column-count error must be located by CSV record number (the
header is record 1, quoted newlines do not advance the number).

The normalize-null tests pin the documented empty-value rule: after stripping
both ends, only an empty result or an ASCII case-insensitive match for
NULL / N/A becomes the empty string; everything else (including surrounding
whitespace, NULLABLE and fullwidth look-alikes) is returned unchanged.
"""

import codecs
import io
import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parent / "csv_cleaner.py"

HEADER = ["name", "note"]
# Text with one real newline embedded between its two lines.
MULTILINE_NOTE = "第一行\n第二行"
QUOTED_NOTE = '他说"好"'

SUCCESS_ROWS = [
    HEADER,
    [" Alice ", "x,y"],          # one plain space on each side of the name
    ["张 三", MULTILINE_NOTE],    # one plain space kept inside the name
    ["   ", QUOTED_NOTE],         # three plain spaces trim down to empty
]

EXPECTED_OUTPUT_ROWS = [
    HEADER,
    ["Alice", "x,y"],
    ["张 三", MULTILINE_NOTE],
    ["", QUOTED_NOTE],
]

# Ten name values exercising the documented normalize-null rule. Rows whose
# stripped name is empty or an ASCII case-insensitive NULL / N/A become the
# empty string; all other rows pass through byte-for-byte, leading and
# trailing whitespace included.
IDEOGRAPHIC_SPACE = "　"  # U+3000 fullwidth space
FULLWIDTH_NULL = "ＮＵＬＬ"  # fullwidth letters, not an ASCII marker
NORMALIZE_NULL_ROWS = [
    HEADER,
    ["", "NULL"],                                  # 1: already empty
    ["   ", "N/A"],                                # 2: empty after strip
    ["NuLl", 'a"b'],                               # 3: NULL ignoring case
    [" n/A ", "plain"],                            # 4: N/A with spaces
    [" NULLABLE ", "kept, comma"],                 # 5: only looks like NULL
    [" xNULLy ", 'he said "hi"'],                  # 6: marker embedded
    [FULLWIDTH_NULL, "line one\nline two"],        # 7: fullwidth letters
    [" N A ", " N/A "],                            # 8: inner space breaks it
    ["  张 三  ", "note nine"],                    # 9: ordinary text
    [IDEOGRAPHIC_SPACE + "NULL" + IDEOGRAPHIC_SPACE,
     "last"],                                      # 10: U+3000 also strips
]

NORMALIZE_NULL_EXPECTED_NAMES = [
    "",        # 1: empty stays empty (not counted as a change)
    "",        # 2
    "",        # 3
    "",        # 4
    " NULLABLE ",
    " xNULLy ",
    FULLWIDTH_NULL,
    " N A ",
    "  张 三  ",
    "",        # 10
]


def encode_csv(rows, *, bom):
    """Serialize rows to CSV bytes, optionally prefixed with a UTF-8 BOM."""
    buffer = io.StringIO()
    csv.writer(buffer).writerows(rows)
    encoding = "utf-8-sig" if bom else "utf-8"
    return buffer.getvalue().encode(encoding)


class CsvCleanerCliTests(unittest.TestCase):
    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.tmpdir = Path(self._tempdir.name)

    def write_input(self, rows, *, bom, tag):
        data = encode_csv(rows, bom=bom)
        path = self.tmpdir / f"input_{tag}.csv"
        path.write_bytes(data)
        return path, data

    def run_cleaner(self, input_path, output_path, *, rule="trim",
                    column="name"):
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--input", str(input_path),
                "--output", str(output_path),
                "--column", column,
                "--rule", rule,
            ],
            cwd=str(self.tmpdir),
            capture_output=True,
        )

    def read_output_records(self, path):
        # Plain utf-8 (not utf-8-sig) so a stray BOM would surface as content.
        with open(path, "r", encoding="utf-8", newline="") as outfile:
            return list(csv.reader(outfile))

    def test_trim_preserves_quoted_fields_with_and_without_bom(self):
        for bom in (False, True):
            with self.subTest(bom=bom):
                tag = "bom" if bom else "nobom"
                input_path, original_bytes = self.write_input(
                    SUCCESS_ROWS, bom=bom, tag=tag
                )
                output_path = self.tmpdir / f"cleaned_{tag}.csv"
                self.assertFalse(output_path.exists())

                result = self.run_cleaner(input_path, output_path)

                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, b"")
                # The whole stdout must parse as one JSON object and nothing
                # else; json.loads rejects any trailing non-whitespace.
                summary = json.loads(result.stdout.decode("utf-8"))
                self.assertEqual(
                    summary, {"rows": 3, "changed_cells": 2}
                )

                self.assertTrue(output_path.exists())
                raw_output = output_path.read_bytes()
                self.assertFalse(raw_output.startswith(codecs.BOM_UTF8))
                # Parsed contents must match regardless of quoting style or
                # line terminator used by the equivalent output CSV.
                self.assertEqual(
                    self.read_output_records(output_path),
                    EXPECTED_OUTPUT_ROWS,
                )

                # The input file is opened read-only: its exact bytes remain.
                self.assertEqual(input_path.read_bytes(), original_bytes)

    def test_column_count_error_uses_csv_record_number_not_physical_line(self):
        # The second record spans two physical lines because of its quoted
        # newline, so the short "Bad" record is physical line 4 but CSV
        # record 3 (the header counts as record 1).
        rows = [
            HEADER,
            ["张 三", MULTILINE_NOTE],
            ["Bad"],
        ]
        input_path, original_bytes = self.write_input(rows, bom=False,
                                                      tag="bad")
        output_path = self.tmpdir / "cleaned_bad.csv"
        self.assertFalse(output_path.exists())

        result = self.run_cleaner(input_path, output_path)

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(
            result.stderr.decode("utf-8"),
            "error: record 3 has 1 field(s), expected 2\n",
        )
        self.assertFalse(output_path.exists())
        self.assertEqual(input_path.read_bytes(), original_bytes)

    def test_normalize_null_rule_with_and_without_bom(self):
        # Only the name column is cleaned: every note value, including the
        # NULL / N/A strings and the quoted comma, quote and embedded
        # newline, must come back exactly as written.
        expected_rows = [HEADER]
        expected_rows.extend(
            [expected_name, row[1]]
            for row, expected_name in zip(
                NORMALIZE_NULL_ROWS[1:], NORMALIZE_NULL_EXPECTED_NAMES
            )
        )

        for bom in (False, True):
            with self.subTest(bom=bom):
                tag = "null_bom" if bom else "null_nobom"
                input_path, original_bytes = self.write_input(
                    NORMALIZE_NULL_ROWS, bom=bom, tag=tag
                )
                output_path = self.tmpdir / f"cleaned_{tag}.csv"
                self.assertFalse(output_path.exists())

                result = self.run_cleaner(
                    input_path, output_path, rule="normalize-null"
                )

                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, b"")
                # stdout must be exactly one JSON object, no other output.
                summary = json.loads(result.stdout.decode("utf-8"))
                # The already-empty first row is not a change; rows 2, 3, 4
                # and 10 are the four cells that change.
                self.assertEqual(
                    summary, {"rows": 10, "changed_cells": 4}
                )

                self.assertTrue(output_path.exists())
                raw_output = output_path.read_bytes()
                self.assertFalse(raw_output.startswith(codecs.BOM_UTF8))
                # Header and record order are unchanged; the quoted notes
                # parse back to their original values.
                self.assertEqual(
                    self.read_output_records(output_path),
                    expected_rows,
                )

                # The input file is opened read-only: its exact bytes remain.
                self.assertEqual(input_path.read_bytes(), original_bytes)

    def test_normalize_null_header_only_file_writes_header_with_zero_counts(
        self,
    ):
        for bom in (False, True):
            with self.subTest(bom=bom):
                tag = "header_bom" if bom else "header_nobom"
                input_path, original_bytes = self.write_input(
                    [HEADER], bom=bom, tag=tag
                )
                output_path = self.tmpdir / f"cleaned_{tag}.csv"

                result = self.run_cleaner(
                    input_path, output_path, rule="normalize-null"
                )

                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, b"")
                self.assertEqual(
                    json.loads(result.stdout.decode("utf-8")),
                    {"rows": 0, "changed_cells": 0},
                )
                # A header-only input still exports the header record.
                self.assertEqual(
                    self.read_output_records(output_path), [HEADER]
                )
                self.assertEqual(input_path.read_bytes(), original_bytes)

    def test_normalize_null_unknown_column_is_case_sensitive(self):
        input_path, original_bytes = self.write_input(
            NORMALIZE_NULL_ROWS, bom=False, tag="wrongcol"
        )
        output_path = self.tmpdir / "cleaned_wrongcol.csv"
        self.assertFalse(output_path.exists())

        result = self.run_cleaner(
            input_path, output_path, rule="normalize-null", column="Name"
        )

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        stderr_text = result.stderr.decode("utf-8")
        self.assertIn("column not found in header", stderr_text)
        self.assertIn("Name", stderr_text)
        self.assertFalse(output_path.exists())
        self.assertEqual(input_path.read_bytes(), original_bytes)


if __name__ == "__main__":
    unittest.main()

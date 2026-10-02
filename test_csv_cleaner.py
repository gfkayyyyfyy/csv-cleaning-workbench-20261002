#!/usr/bin/env python3
"""Regression tests for the csv_cleaner.py command-line entry point.

Run from the project root:

    python -m unittest discover

The tests exercise only the documented public CLI:

* trim: quoted fields containing commas, newlines and double quotes must
  survive unchanged, and a structural column-count error must be located by
  CSV record number (the header is record 1, quoted newlines do not advance
  the number).
* normalize-null: the documented null markers (empty / whitespace-only,
  NULL and N/A matched case-insensitively on ASCII letters, with Unicode
  str.strip() trimming at both ends) become empty strings; near-miss text
  is preserved verbatim including surrounding and internal whitespace.
  Also covers the header-only summary and case-sensitive column lookup.
* normalize-date: blank cells become empty, real Gregorian dates spelled
  YYYY-MM-DD or DD/MM/YYYY (ASCII digits, zero-padded) normalize to
  YYYY-MM-DD, and the first invalid date (internal whitespace, unpadded
  numbers, time suffixes, NULL/N/A text, nonexistent calendar dates)
  fails by CSV record number without exporting anything. A year-boundary
  regression pins the documented 0001-9999 range: both endpoints convert
  (the low year keeps four digits), 2000-02-29 is a century leap day in
  either spelling, and 1900-02-29, 29/02/2100, 0000-01-01 and
  01/01/10000 are each rejected at record 3 without partial output.
* --null-marker: repeatable custom whole-value markers for the
  normalize-null rule. They coexist with the default blank / NULL / N/A
  handling; duplicate markers and markers equivalent to a default one
  collapse without inflating the change count, matching strips both ends
  and ignores ASCII letter case only (so " Ä " is not the marker "ä"),
  and marker text embedded in a larger value never matches. Runs are
  checked with and without a UTF-8 BOM (output is always BOM-free, header
  and record order unchanged), the untouched note column carries marker
  text, commas, double quotes and a real newline, and the input bytes
  stay unchanged. A missing marker value, a value empty after str.strip()
  (including ideographic-space-only values), or use with trim /
  normalize-date fails with exit code 2, empty stdout, the corresponding
  reason on stderr, no Python traceback, no output file and untouched
  input bytes -- including for a header-only input; a header-only input
  with valid markers exports just the header with both counts at 0.
* invalid inputs (zero-byte file, BOM-only file, empty and duplicate
  header column names, an unterminated quoted field, invalid UTF-8 bytes
  and a record with too many fields following a record containing a
  quoted newline) fail with exit code 2, empty stdout and a categorized
  reason on stderr without a Python traceback; no output file is left
  behind, even when an earlier record could already have been cleaned,
  and the input bytes stay untouched.
* output path protection: an output path naming an existing regular
  file (valid CSV or non-UTF-8 bytes), or resolving to the input file
  itself (identical spelling or via a "." path segment), is rejected
  with exit code 2, empty stdout and the documented reason on stderr;
  the existing target and the input keep their exact bytes and no extra
  files appear. A fresh output path still exports successfully.
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

# normalize-null sample: ten name values exercising each documented rule
# boundary. Notes carry the quoting hazards (commas, double quotes, real
# newlines) plus literal NULL / N/A text, which must never be normalized
# because only the named column is cleaned.
NULL_ROWS = [
    HEADER,
    ["", "NULL"],                                  # already empty: not a change
    ["   ", "N/A"],                                # whitespace-only -> empty
    ["NuLl", "plain"],                             # mixed-case NULL -> empty
    [" n/A ", "a,b"],                              # trimmed N/A -> empty
    [" NULLABLE ", QUOTED_NOTE],                   # marker plus letters: kept
    [" xNULLy ", MULTILINE_NOTE],                  # marker embedded: kept
    ["ＮＵＬＬ", "fullwidth letters, not ASCII"],  # U+FF2E...: not a match
    [" N A ", "internal gap, not a marker"],       # internal space: kept
    ["  张 三  ", "kept, spaces and all"],         # ordinary text kept as-is
    ["　NULL　", "ideographic spaces around"],     # U+3000 stripped: -> empty
]

NULL_EXPECTED_NAMES = [
    "",        # 1: empty stays empty (not counted as a change)
    "",        # 2: three ASCII spaces
    "",        # 3: NuLl
    "",        # 4: " n/A "
    " NULLABLE ",   # 5: verbatim
    " xNULLy ",     # 6: verbatim
    "ＮＵＬＬ",      # 7: verbatim
    " N A ",        # 8: verbatim
    "  张 三  ",     # 9: verbatim, spaces kept
    "",        # 10: U+3000-padded NULL
]
# Rows 2, 3, 4 and 10 actually change; row 1 was already empty.
NULL_EXPECTED_CHANGED = 4

# normalize-date sample: the due_date column exercises both accepted
# spellings plus blank cells; the note column carries the quoting hazards
# (commas, double quotes, a real newline) and must round-trip untouched.
DATE_HEADER = ["due_date", "note"]
DATE_ROWS = [
    DATE_HEADER,
    [" 29/02/2024 ", "first, with comma"],       # DD/MM/YYYY, padded ends
    ["2024-03-01", '他说"好"\n第二行'],            # already ISO, quoted note
    ["   ", "plain"],                            # whitespace-only -> empty
    ["", "last"],                                # already empty: not a change
]
DATE_EXPECTED_DATES = ["2024-02-29", "2024-03-01", "", ""]
# Rows 1 and 3 change; row 2 was already ISO and row 4 already empty.
DATE_EXPECTED_CHANGED = 2

# Cell values that must all be rejected as invalid dates.
INVALID_DATE_VALUES = [
    "31/02/2024",        # February never has 31 days
    "29/02/2023",        # 2023 is not a leap year
    "0000-01-01",        # year 0000 is outside 0001-9999
    "2024-3-1",          # unpadded month and day
    "2024-03-01 10:30",  # time suffix
    "2024 -03-01",       # internal whitespace
    "NULL",              # null marker text is not a date
    "N/A",
    "２０２４-０３-０１",   # fullwidth digits are not ASCII digits
    "2024/03/01",        # slashes only in DD/MM/YYYY order
    "01-03-2024",        # dashes only in YYYY-MM-DD order
]

# Year-boundary and century-leap regression for the documented 0001-9999
# range. The four date values hit: the lowest year (kept four digits on
# export), the highest year, the year-2000 century leap day in the
# DD/MM/YYYY spelling with one space on each side, and that same leap day
# already spelled ISO (so it must not count as a change).
BOUNDARY_DATE_ROWS = [
    DATE_HEADER,
    ["01/01/0001", 'he said "hi, all"\nline two'],  # year 0001 endpoint
    ["9999-12-31", "a,b,c"],                        # year 9999 endpoint
    [" 29/02/2000 ", 'quote "x", comma and\nwrap'],  # century leap day
    ["2000-02-29", "plain"],                        # already normalized
]
BOUNDARY_EXPECTED_DATES = [
    "0001-01-01",
    "9999-12-31",
    "2000-02-29",
    "2000-02-29",
]
# Only rows 1 and 3 change; the two ISO values were already normalized.
BOUNDARY_EXPECTED_CHANGED = 2

# Out-of-range and non-leap century cases. Each run puts one cleanable
# record first (its note holds a real newline), the candidate value at
# record 3, and a second invalid date 31/04/2000 at record 4 which must
# never be reported: the first failure aborts the run.
BOUNDARY_INVALID_VALUES = [
    "1900-02-29",   # 1900 is divisible by 100 but not 400: not a leap year
    "29/02/2100",   # 2100 is likewise not a leap year
    "0000-01-01",   # year 0000 is one below the documented range
    "01/01/10000",  # a five-digit year is one above the documented range
]

# --null-marker sample: five repeatable custom markers, two of which
# overlap each other or a default marker after normalization, proving the
# documented de-duplication: " MISSING " and "missing" strip/lower to the
# same key (one match, counted once), and "null" is exactly equivalent to
# the default NULL marker (still empties the cell, but adds no behavior).
CUSTOM_MARKERS = [" MISSING ", "missing", "待补", "null", "ä"]

# Nine name values, one row per documented boundary:
CUSTOM_NULL_ROWS = [
    HEADER,
    ["", "null 与 n/a,文字"],                       # blank default: empty
    ["   ", 'he said "hi, all"'],                  # whitespace default: empty
    [" NuLl ", "line1\nline2"],                    # default NULL, padded+case
    ["N/A", "普通,not a marker"],                   # default N/A: empty
    [" missing ", '"quoted marker text"'],         # custom marker, padded
    ["待补", "待补 stays here, embedded 待补 text"],  # custom Chinese marker
    [" MISSINGLY ", "prefix MISSING suffix"],      # superstring: kept whole
    [" Ä ", "ä appears here too"],                 # non-ASCII case: kept
    [" 普通 ", "plain, with comma and 普通 text"],   # ordinary text: kept
]
# The first six names normalize to empty strings (the first one was
# already empty, so only five cells change); the last three survive
# character-for-character including their surrounding spaces.
CUSTOM_NULL_EXPECTED_NAMES = [
    "",              # 1: empty stays empty (not counted as a change)
    "",              # 2: three ASCII spaces
    "",              # 3: " NuLl " via the default NULL marker
    "",              # 4: N/A via the default marker
    "",              # 5: " missing " via a custom marker
    "",              # 6: 待补 via a custom marker
    " MISSINGLY ",   # 7: whole-value match only: verbatim
    " Ä ",           # 8: ASCII-case folding only: verbatim
    " 普通 ",         # 9: ordinary text: verbatim
]
CUSTOM_NULL_EXPECTED_CHANGED = 5


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

    def write_raw_input(self, data, *, tag):
        """Write arbitrary raw bytes as an input file and report its path."""
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

    def test_normalize_null_markers_with_and_without_bom(self):
        for bom in (False, True):
            with self.subTest(bom=bom):
                tag = "null_bom" if bom else "null_nobom"
                input_path, original_bytes = self.write_input(
                    NULL_ROWS, bom=bom, tag=tag
                )
                output_path = self.tmpdir / f"cleaned_{tag}.csv"
                self.assertFalse(output_path.exists())

                result = self.run_cleaner(
                    input_path, output_path, rule="normalize-null"
                )

                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, b"")
                # stdout must consist of exactly one JSON object and nothing
                # else; json.loads rejects trailing non-whitespace.
                summary = json.loads(result.stdout.decode("utf-8"))
                self.assertEqual(
                    summary,
                    {"rows": 10,
                     "changed_cells": NULL_EXPECTED_CHANGED},
                )

                self.assertTrue(output_path.exists())
                raw_output = output_path.read_bytes()
                self.assertFalse(raw_output.startswith(codecs.BOM_UTF8))

                output_rows = self.read_output_records(output_path)
                # Header and record order are unchanged.
                self.assertEqual(output_rows[0], HEADER)
                self.assertEqual(len(output_rows), 11)
                # Name column follows the explicit per-row expectations.
                self.assertEqual(
                    [row[0] for row in output_rows[1:]],
                    NULL_EXPECTED_NAMES,
                )
                # The note column is never cleaned (only --column name is),
                # so every note value, including NULL/N/A text, commas,
                # quotes and embedded newlines, must round-trip byte-for-byte
                # in terms of parsed values.
                self.assertEqual(
                    [row[1] for row in output_rows],
                    [row[1] for row in NULL_ROWS],
                )

                # The input file is opened read-only: exact bytes remain.
                self.assertEqual(input_path.read_bytes(), original_bytes)

    def test_normalize_null_header_only_file_exports_header(self):
        input_path, original_bytes = self.write_input(
            [HEADER], bom=False, tag="null_header_only"
        )
        output_path = self.tmpdir / "cleaned_null_header_only.csv"
        self.assertFalse(output_path.exists())

        result = self.run_cleaner(
            input_path, output_path, rule="normalize-null"
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(
            json.loads(result.stdout.decode("utf-8")),
            {"rows": 0, "changed_cells": 0},
        )
        self.assertTrue(output_path.exists())
        self.assertFalse(
            output_path.read_bytes().startswith(codecs.BOM_UTF8)
        )
        self.assertEqual(
            self.read_output_records(output_path), [HEADER]
        )
        self.assertEqual(input_path.read_bytes(), original_bytes)

    def test_normalize_null_column_lookup_is_case_sensitive(self):
        # Header spells the column "name"; asking for "Name" must fail
        # without touching the input or creating the output file.
        input_path, original_bytes = self.write_input(
            NULL_ROWS, bom=False, tag="null_bad_column"
        )
        output_path = self.tmpdir / "cleaned_null_bad_column.csv"
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

    def test_normalize_date_with_and_without_bom(self):
        for bom in (False, True):
            with self.subTest(bom=bom):
                tag = "date_bom" if bom else "date_nobom"
                input_path, original_bytes = self.write_input(
                    DATE_ROWS, bom=bom, tag=tag
                )
                output_path = self.tmpdir / f"cleaned_{tag}.csv"
                self.assertFalse(output_path.exists())

                result = self.run_cleaner(
                    input_path, output_path,
                    rule="normalize-date", column="due_date",
                )

                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, b"")
                # stdout must consist of exactly one JSON object and nothing
                # else; json.loads rejects trailing non-whitespace.
                summary = json.loads(result.stdout.decode("utf-8"))
                self.assertEqual(
                    summary,
                    {"rows": 4, "changed_cells": DATE_EXPECTED_CHANGED},
                )

                self.assertTrue(output_path.exists())
                raw_output = output_path.read_bytes()
                self.assertFalse(raw_output.startswith(codecs.BOM_UTF8))

                output_rows = self.read_output_records(output_path)
                # Header and record order are unchanged.
                self.assertEqual(output_rows[0], DATE_HEADER)
                self.assertEqual(len(output_rows), 5)
                # The due_date column is normalized per row.
                self.assertEqual(
                    [row[0] for row in output_rows[1:]],
                    DATE_EXPECTED_DATES,
                )
                # The note column is never cleaned, so commas, double
                # quotes and the embedded newline round-trip byte-for-byte
                # in terms of parsed values.
                self.assertEqual(
                    [row[1] for row in output_rows],
                    [row[1] for row in DATE_ROWS],
                )

                # The input file is opened read-only: exact bytes remain.
                self.assertEqual(input_path.read_bytes(), original_bytes)

    def test_normalize_date_header_only_file_exports_header(self):
        input_path, original_bytes = self.write_input(
            [DATE_HEADER], bom=False, tag="date_header_only"
        )
        output_path = self.tmpdir / "cleaned_date_header_only.csv"
        self.assertFalse(output_path.exists())

        result = self.run_cleaner(
            input_path, output_path,
            rule="normalize-date", column="due_date",
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(
            json.loads(result.stdout.decode("utf-8")),
            {"rows": 0, "changed_cells": 0},
        )
        self.assertTrue(output_path.exists())
        self.assertFalse(
            output_path.read_bytes().startswith(codecs.BOM_UTF8)
        )
        self.assertEqual(
            self.read_output_records(output_path), [DATE_HEADER]
        )
        self.assertEqual(input_path.read_bytes(), original_bytes)

    def test_normalize_date_first_invalid_value_fails_by_record_number(self):
        # Record 2's note contains a quoted real newline, so it spans two
        # physical lines but counts as one CSV record. Record 3 carries
        # the impossible date 31/02/2024; it must be reported as record 3
        # and the cleanable record 2 must not be exported ahead of it.
        rows = [
            DATE_HEADER,
            [" 29/02/2024 ", MULTILINE_NOTE],
            ["31/02/2024", "bad date"],
            ["2024-03-01", "ok"],
        ]
        input_path, original_bytes = self.write_input(
            rows, bom=False, tag="date_invalid"
        )
        output_path = self.tmpdir / "cleaned_date_invalid.csv"
        self.assertFalse(output_path.exists())

        result = self.run_cleaner(
            input_path, output_path,
            rule="normalize-date", column="due_date",
        )

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        stderr_text = result.stderr.decode("utf-8")
        self.assertIn("invalid date", stderr_text)
        self.assertIn("due_date", stderr_text)
        self.assertIn("record 3", stderr_text)
        self.assertNotIn("Traceback", stderr_text)
        self.assertFalse(output_path.exists())
        self.assertEqual(input_path.read_bytes(), original_bytes)

    def test_normalize_date_rejects_each_invalid_spelling(self):
        # Every documented invalid spelling fails the run when it appears
        # as the first data record (CSV record 2).
        for value in INVALID_DATE_VALUES:
            with self.subTest(value=value):
                tag = f"date_bad_{INVALID_DATE_VALUES.index(value)}"
                input_path, original_bytes = self.write_input(
                    [DATE_HEADER, [value, "note"]], bom=False, tag=tag
                )
                output_path = self.tmpdir / f"cleaned_{tag}.csv"
                self.assertFalse(output_path.exists())

                result = self.run_cleaner(
                    input_path, output_path,
                    rule="normalize-date", column="due_date",
                )

                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, b"")
                stderr_text = result.stderr.decode("utf-8")
                self.assertIn("invalid date", stderr_text)
                self.assertIn("due_date", stderr_text)
                self.assertIn("record 2", stderr_text)
                self.assertNotIn("Traceback", stderr_text)
                self.assertFalse(output_path.exists())
                self.assertEqual(input_path.read_bytes(), original_bytes)

    def test_normalize_date_year_boundaries_and_century_leap_day(self):
        # Acceptance for the README's 0001-9999 range claim: both year
        # endpoints convert, the year-0001 value keeps four digits, and
        # 2000-02-29 (divisible by 400) is a leap day in either spelling.
        # The last value is already ISO and must not count as a change.
        for bom in (False, True):
            with self.subTest(bom=bom):
                tag = "date_boundary_bom" if bom else "date_boundary_nobom"
                input_path, original_bytes = self.write_input(
                    BOUNDARY_DATE_ROWS, bom=bom, tag=tag
                )
                output_path = self.tmpdir / f"cleaned_{tag}.csv"
                self.assertFalse(output_path.exists())

                result = self.run_cleaner(
                    input_path, output_path,
                    rule="normalize-date", column="due_date",
                )

                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, b"")
                # stdout must consist of exactly one JSON object and
                # nothing else; json.loads rejects trailing non-whitespace.
                self.assertEqual(
                    json.loads(result.stdout.decode("utf-8")),
                    {"rows": 4,
                     "changed_cells": BOUNDARY_EXPECTED_CHANGED},
                )

                self.assertTrue(output_path.exists())
                raw_output = output_path.read_bytes()
                # The export is always BOM-free UTF-8, even for BOM input.
                self.assertFalse(raw_output.startswith(codecs.BOM_UTF8))

                output_rows = self.read_output_records(output_path)
                # Header and record order are unchanged.
                self.assertEqual(output_rows[0], DATE_HEADER)
                self.assertEqual(len(output_rows), 5)
                # Dates normalize to the expected spellings; year 0001
                # keeps its leading zeroes through the ISO format.
                self.assertEqual(
                    [row[0] for row in output_rows[1:]],
                    BOUNDARY_EXPECTED_DATES,
                )
                # The note column is never cleaned. Parsed field values
                # must preserve commas, double quotes and the embedded
                # real newlines exactly.
                self.assertEqual(
                    [row[1] for row in output_rows],
                    [row[1] for row in BOUNDARY_DATE_ROWS],
                )

                # The input file is opened read-only: exact bytes remain.
                self.assertEqual(input_path.read_bytes(), original_bytes)

    def test_normalize_date_rejects_outside_range_and_non_leap_centuries(
        self
    ):
        # 1900 and 2100 are divisible by 100 but not 400, so their
        # February has no 29th; year 0000 and a five-digit year fall
        # outside the documented 0001-9999 range. Each candidate sits at
        # record 3 after one cleanable record and before 31/04/2000, so
        # the first-error-only behavior is checked as well.
        for value in BOUNDARY_INVALID_VALUES:
            with self.subTest(value=value):
                tag = (
                    "date_boundary_bad_"
                    + str(BOUNDARY_INVALID_VALUES.index(value))
                )
                rows = [
                    DATE_HEADER,
                    [" 29/02/2000 ", MULTILINE_NOTE],
                    [value, "candidate"],
                    ["31/04/2000", "never reported"],
                ]
                input_path, original_bytes = self.write_input(
                    rows, bom=False, tag=tag
                )
                output_path = self.tmpdir / f"cleaned_{tag}.csv"
                self.assertFalse(output_path.exists())

                result = self.run_cleaner(
                    input_path, output_path,
                    rule="normalize-date", column="due_date",
                )

                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, b"")
                stderr_text = result.stderr.decode("utf-8")
                self.assertIn("invalid date", stderr_text)
                self.assertIn("due_date", stderr_text)
                self.assertIn("record 3", stderr_text)
                # The message quotes the first offending value verbatim.
                self.assertIn(value, stderr_text)
                # Only the first invalid date is reported; the later
                # 31/04/2000 record must not appear in the message.
                self.assertNotIn("record 4", stderr_text)
                self.assertNotIn("31/04/2000", stderr_text)
                self.assertNotIn("Traceback", stderr_text)
                # The cleanable record 2 must not have been exported.
                self.assertFalse(output_path.exists())
                self.assertEqual(
                    input_path.read_bytes(), original_bytes
                )

    def assert_invalid_input_fails(self, input_path, output_path,
                                   original_bytes, fragments):
        """Run one invalid-input case and assert the documented failure.

        Exit code 2, empty stdout, each given reason fragment on stderr,
        no Python traceback, no output file left behind, and input bytes
        unchanged. Returns the completed process for extra assertions.
        """
        result = self.run_cleaner(input_path, output_path)

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        stderr_text = result.stderr.decode("utf-8", errors="replace")
        for fragment in fragments:
            self.assertIn(fragment, stderr_text)
        # The failure must come through the documented error path: no
        # interpreter traceback or an uncaught exception type line.
        self.assertNotIn("Traceback", stderr_text)
        self.assertNotIn("Error:", stderr_text)
        # Validation/parsing happens before anything is exported, so a
        # failure must never leave a partially cleaned file behind...
        self.assertFalse(
            output_path.exists(),
            "a failed run must not leave an output file behind",
        )
        # ...and the input file is opened read-only, so its exact bytes
        # remain unchanged.
        self.assertEqual(input_path.read_bytes(), original_bytes)
        return result

    def test_zero_byte_file_reports_missing_header(self):
        input_path, original_bytes = self.write_raw_input(
            b"", tag="zero_byte"
        )
        output_path = self.tmpdir / "cleaned_zero_byte.csv"
        self.assertFalse(output_path.exists())

        self.assert_invalid_input_fails(
            input_path, output_path, original_bytes,
            ["input is empty", "no header"],
        )

    def test_bom_only_file_reports_missing_header(self):
        # A file containing only the UTF-8 BOM has no records once the BOM
        # is stripped, so it must be reported as having no header rather
        # than crashing or exporting anything.
        input_path, original_bytes = self.write_raw_input(
            codecs.BOM_UTF8, tag="bom_only"
        )
        output_path = self.tmpdir / "cleaned_bom_only.csv"
        self.assertFalse(output_path.exists())

        self.assert_invalid_input_fails(
            input_path, output_path, original_bytes,
            ["input is empty", "no header"],
        )

    def test_header_with_empty_column_name_is_rejected(self):
        input_path, original_bytes = self.write_raw_input(
            b"name,\n", tag="empty_name"
        )
        output_path = self.tmpdir / "cleaned_empty_name.csv"
        self.assertFalse(output_path.exists())

        self.assert_invalid_input_fails(
            input_path, output_path, original_bytes,
            ["header contains an empty column name"],
        )

    def test_header_with_duplicate_column_names_is_rejected(self):
        input_path, original_bytes = self.write_raw_input(
            b"name,name\n", tag="duplicate_name"
        )
        output_path = self.tmpdir / "cleaned_duplicate_name.csv"
        self.assertFalse(output_path.exists())

        self.assert_invalid_input_fails(
            input_path, output_path, original_bytes,
            ["header contains duplicate column names"],
        )

    def test_unterminated_quoted_field_fails_without_partial_output(self):
        # The first data record (" Alice ") would be cleanable; the second
        # opens a quoted field that is still open at end of file. The parse
        # failure must surface as exit code 2 and must not export the
        # already-cleaned Alice record. Check both ways EOF can arrive:
        # right inside the field, and after one more physical newline.
        good_prefix = encode_csv(
            [HEADER, [" Alice ", "ok"]], bom=False
        )
        for suffix, style in ((b"", "eof_inside_quotes"),
                              (b"\n", "eof_after_newline")):
            with self.subTest(style=style):
                input_path, original_bytes = self.write_raw_input(
                    good_prefix + b'Bob,"still quoting' + suffix,
                    tag=f"unclosed_{style}",
                )
                output_path = self.tmpdir / f"cleaned_unclosed_{style}.csv"
                self.assertFalse(output_path.exists())

                self.assert_invalid_input_fails(
                    input_path, output_path, original_bytes,
                    ["cannot parse CSV", "unexpected end of data"],
                )

    def test_invalid_utf8_byte_fails_without_partial_output(self):
        # A valid header and a cleanable first record, then a record
        # carrying the invalid UTF-8 byte 0xFF. The decode failure must
        # win and no cleaned version of the first record may be exported.
        good_prefix = encode_csv(
            [HEADER, [" Alice ", "ok"]], bom=False
        )
        input_path, original_bytes = self.write_raw_input(
            good_prefix + b"Bob,\xff\n", tag="bad_utf8"
        )
        output_path = self.tmpdir / "cleaned_bad_utf8.csv"
        self.assertFalse(output_path.exists())

        self.assert_invalid_input_fails(
            input_path, output_path, original_bytes,
            ["not valid UTF-8", "0xff"],
        )

    def test_too_many_fields_after_quoted_newline_record(self):
        # Record 2's note contains a quoted real newline, so it spans two
        # physical lines but counts as one CSV record. Record 3 carries an
        # extra field; it must be reported as record 3 with 3 fields
        # (expected 2), the quoted newline must not be miscounted as a
        # record boundary, and the cleanable Alice record in record 2
        # must not be exported ahead of the failure.
        data = encode_csv(
            [HEADER, [" Alice ", MULTILINE_NOTE]], bom=False
        ) + b"Bob,z,extra\n"
        input_path, original_bytes = self.write_raw_input(
            data, tag="extra_fields"
        )
        output_path = self.tmpdir / "cleaned_extra_fields.csv"
        self.assertFalse(output_path.exists())

        result = self.assert_invalid_input_fails(
            input_path, output_path, original_bytes,
            ["record 3", "3 field(s)", "expected 2"],
        )
        self.assertEqual(
            result.stderr.decode("utf-8"),
            "error: record 3 has 3 field(s), expected 2\n",
        )


class NullMarkerCliTests(unittest.TestCase):
    """Coverage for the repeatable --null-marker option.

    The option is a public, documented feature of normalize-null but had
    no command-line regression coverage. Every test here goes through the
    public CLI with small CSV files prepared in a temporary directory; no
    external files or network are used. Results are judged on parsed CSV
    fields and the parsed JSON object, so equivalent quoting styles and
    JSON key order are irrelevant.
    """

    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.tmpdir = Path(self._tempdir.name)

    def write_input(self, rows, *, bom, tag):
        data = encode_csv(rows, bom=bom)
        path = self.tmpdir / f"input_{tag}.csv"
        path.write_bytes(data)
        return path, data

    def run_cleaner(self, input_path, output_path, *, markers,
                    rule="normalize-null", column="name"):
        argv = [
            sys.executable,
            str(SCRIPT_PATH),
            "--input", str(input_path),
            "--output", str(output_path),
            "--column", column,
            "--rule", rule,
        ]
        # A None entry stands for the bare flag with no following value.
        for marker in markers:
            argv.append("--null-marker")
            if marker is not None:
                argv.append(marker)
        return subprocess.run(
            argv, cwd=str(self.tmpdir), capture_output=True
        )

    def read_output_records(self, path):
        # Plain utf-8 (not utf-8-sig) so a stray BOM would surface as content.
        with open(path, "r", encoding="utf-8", newline="") as outfile:
            return list(csv.reader(outfile))

    def test_custom_null_markers_with_and_without_bom(self):
        for bom in (False, True):
            with self.subTest(bom=bom):
                tag = "marker_bom" if bom else "marker_nobom"
                input_path, original_bytes = self.write_input(
                    CUSTOM_NULL_ROWS, bom=bom, tag=tag
                )
                output_path = self.tmpdir / f"cleaned_{tag}.csv"
                self.assertFalse(output_path.exists())

                result = self.run_cleaner(
                    input_path, output_path, markers=CUSTOM_MARKERS
                )

                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, b"")
                # stdout must consist of exactly one JSON object and
                # nothing else; json.loads rejects trailing non-whitespace.
                self.assertEqual(
                    json.loads(result.stdout.decode("utf-8")),
                    {"rows": 9,
                     "changed_cells": CUSTOM_NULL_EXPECTED_CHANGED},
                )

                self.assertTrue(output_path.exists())
                raw_output = output_path.read_bytes()
                # The export is always BOM-free UTF-8, even for BOM input.
                self.assertFalse(raw_output.startswith(codecs.BOM_UTF8))

                output_rows = self.read_output_records(output_path)
                # Header and record order are unchanged.
                self.assertEqual(output_rows[0], HEADER)
                self.assertEqual(len(output_rows), 10)
                # The first six names become empty strings; the last
                # three survive character-for-character with spaces.
                self.assertEqual(
                    [row[0] for row in output_rows[1:]],
                    CUSTOM_NULL_EXPECTED_NAMES,
                )
                # The note column is never cleaned. Marker text, commas,
                # double quotes and the embedded real newline must all
                # round-trip unchanged in terms of parsed field values.
                self.assertEqual(
                    [row[1] for row in output_rows],
                    [row[1] for row in CUSTOM_NULL_ROWS],
                )

                # The input file is opened read-only: exact bytes remain.
                self.assertEqual(input_path.read_bytes(), original_bytes)

    def test_valid_markers_header_only_file_exports_header(self):
        input_path, original_bytes = self.write_input(
            [HEADER], bom=False, tag="marker_header_only"
        )
        output_path = self.tmpdir / "cleaned_marker_header_only.csv"
        self.assertFalse(output_path.exists())

        result = self.run_cleaner(
            input_path, output_path,
            markers=[" MISSING ", "待补", "null"],
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(
            json.loads(result.stdout.decode("utf-8")),
            {"rows": 0, "changed_cells": 0},
        )
        self.assertTrue(output_path.exists())
        self.assertFalse(
            output_path.read_bytes().startswith(codecs.BOM_UTF8)
        )
        self.assertEqual(
            self.read_output_records(output_path), [HEADER]
        )
        self.assertEqual(input_path.read_bytes(), original_bytes)

    # (label, --null-marker values (None = bare flag), rule, fragments
    # that must each appear on stderr).
    INVALID_MARKER_SCENARIOS = [
        ("missing_value", [None], "normalize-null",
         ["--null-marker", "expected one argument"]),
        ("empty_string", [""], "normalize-null",
         ["--null-marker", "non-empty",
          "stripping surrounding whitespace"]),
        # Two ideographic spaces U+3000 are non-empty raw arguments but
        # empty after str.strip(); they must be rejected the same way.
        ("fullwidth_space_only", ["　　"], "normalize-null",
         ["--null-marker", "non-empty",
          "stripping surrounding whitespace"]),
        ("with_trim", ["x"], "trim",
         ["--null-marker can only be used with --rule normalize-null"]),
        ("with_normalize_date", ["x"], "normalize-date",
         ["--null-marker can only be used with --rule normalize-null"]),
    ]

    def assert_invalid_markers_rejected(self, rows, *, bom, input_tag):
        input_path, original_bytes = self.write_input(
            rows, bom=bom, tag=input_tag
        )
        for label, markers, rule, fragments in self.INVALID_MARKER_SCENARIOS:
            with self.subTest(label=label):
                output_path = self.tmpdir / f"cleaned_{input_tag}_{label}.csv"
                self.assertFalse(output_path.exists())

                result = self.run_cleaner(
                    input_path, output_path, markers=markers, rule=rule
                )

                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, b"")
                stderr_text = result.stderr.decode("utf-8")
                for fragment in fragments:
                    self.assertIn(fragment, stderr_text)
                # The failure must come through the documented error
                # path: no interpreter traceback.
                self.assertNotIn("Traceback", stderr_text)
                # Parameter validation precedes every export, so no
                # output file may be created...
                self.assertFalse(output_path.exists())
                # ...and the input is opened read-only: bytes unchanged.
                self.assertEqual(
                    input_path.read_bytes(), original_bytes
                )

    def test_invalid_markers_rejected_on_data_file(self):
        self.assert_invalid_markers_rejected(
            CUSTOM_NULL_ROWS, bom=False, input_tag="marker_bad_data"
        )

    def test_invalid_markers_rejected_on_header_only_file(self):
        # A perfectly valid header-only input must not make any of the
        # invalid parameter combinations acceptable.
        self.assert_invalid_markers_rejected(
            [HEADER], bom=False, input_tag="marker_bad_header"
        )


class OutputPathProtectionTests(unittest.TestCase):
    """Output-path protection: existing files and same-path outputs.

    Each scenario runs in its own temporary directory with a valid input
    CSV whose named column exists and holds at least one cleanable value,
    so no input-side validation can fail first and mask the path checks.
    """

    def make_workspace(self):
        """Return a fresh temporary directory dedicated to one scenario."""
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        return Path(tempdir.name)

    @staticmethod
    def cleanable_rows(rule):
        # A valid header plus one data record whose name cell the given
        # rule must change, so a successful run would have work to do.
        if rule == "trim":
            return [HEADER, [" Alice ", "x,y"]]
        if rule == "normalize-date":
            return [HEADER, [" 29/02/2024 ", "x,y"]]
        return [HEADER, [" n/A ", "x,y"]]

    def write_cleanable_input(self, workspace, rule):
        input_bytes = encode_csv(self.cleanable_rows(rule), bom=False)
        input_path = workspace / "input.csv"
        input_path.write_bytes(input_bytes)
        return input_path, input_bytes

    def run_cleaner(self, input_path, output_path, *, rule, cwd):
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--input", str(input_path),
                "--output", str(output_path),
                "--column", "name",
                "--rule", rule,
            ],
            cwd=str(cwd),
            capture_output=True,
        )

    def assert_refused(self, result, workspace, expected_files, fragment):
        """Assert the documented refusal shape for one rejected run."""
        self.assertEqual(result.returncode, 2)
        # Empty stdout also means no success summary was printed.
        self.assertEqual(result.stdout, b"")
        stderr_text = result.stderr.decode("utf-8", errors="replace")
        self.assertIn(fragment, stderr_text)
        self.assertNotIn("Traceback", stderr_text)
        # No extra cleaned files may be left behind in the workspace.
        self.assertEqual(
            sorted(p.name for p in workspace.iterdir()),
            sorted(expected_files),
        )

    def test_existing_output_file_is_never_overwritten(self):
        # The pre-existing target is either a valid CSV file or a file
        # holding non-UTF-8 bytes; neither may be read into, truncated or
        # replaced, for either cleaning rule.
        targets = {
            "valid_csv": encode_csv([HEADER, ["keep", "me"]], bom=False),
            "non_utf8_bytes": b"\xff\xfe not valid utf-8",
        }
        for rule in ("trim", "normalize-null", "normalize-date"):
            for target_kind, target_bytes in targets.items():
                with self.subTest(rule=rule, target=target_kind):
                    workspace = self.make_workspace()
                    input_path, input_bytes = self.write_cleanable_input(
                        workspace, rule
                    )
                    output_path = workspace / "cleaned.csv"
                    output_path.write_bytes(target_bytes)

                    result = self.run_cleaner(
                        input_path, output_path, rule=rule, cwd=workspace
                    )

                    self.assert_refused(
                        result, workspace,
                        ["cleaned.csv", "input.csv"],
                        "output file already exists",
                    )
                    # Target and input survive byte-for-byte.
                    self.assertEqual(output_path.read_bytes(), target_bytes)
                    self.assertEqual(input_path.read_bytes(), input_bytes)

    def test_output_path_identical_to_input_is_rejected(self):
        for rule in ("trim", "normalize-null", "normalize-date"):
            with self.subTest(rule=rule):
                workspace = self.make_workspace()
                input_path, input_bytes = self.write_cleanable_input(
                    workspace, rule
                )

                result = self.run_cleaner(
                    input_path, input_path, rule=rule, cwd=workspace
                )

                self.assert_refused(
                    result, workspace, ["input.csv"],
                    "output path must be different from the input path",
                )
                # The input is neither deleted nor rewritten.
                self.assertEqual(input_path.read_bytes(), input_bytes)

    def test_output_path_with_dot_segment_aliasing_input_is_rejected(self):
        for rule in ("trim", "normalize-null", "normalize-date"):
            with self.subTest(rule=rule):
                workspace = self.make_workspace()
                input_path, input_bytes = self.write_cleanable_input(
                    workspace, rule
                )
                # A different spelling containing a "." segment that still
                # resolves to the input file (os.path.join keeps the dot,
                # unlike pathlib).
                aliased_output = os.path.join(
                    str(workspace), ".", input_path.name
                )
                self.assertNotEqual(aliased_output, str(input_path))

                result = self.run_cleaner(
                    input_path, aliased_output, rule=rule, cwd=workspace
                )

                self.assert_refused(
                    result, workspace, ["input.csv"],
                    "output path must be different from the input path",
                )
                self.assertEqual(input_path.read_bytes(), input_bytes)

    def test_fresh_output_path_exports_cleaned_csv(self):
        # Control case: the same cleanable input exports successfully when
        # the output path does not exist yet.
        workspace = self.make_workspace()
        input_path, input_bytes = self.write_cleanable_input(
            workspace, "trim"
        )
        output_path = workspace / "cleaned.csv"
        self.assertFalse(output_path.exists())

        result = self.run_cleaner(
            input_path, output_path, rule="trim", cwd=workspace
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        # stdout is exactly one JSON object; key order is not fixed.
        self.assertEqual(
            json.loads(result.stdout.decode("utf-8")),
            {"rows": 1, "changed_cells": 1},
        )
        raw_output = output_path.read_bytes()
        self.assertFalse(raw_output.startswith(codecs.BOM_UTF8))
        with open(output_path, "r", encoding="utf-8", newline="") as outfile:
            self.assertEqual(
                list(csv.reader(outfile)),
                [HEADER, ["Alice", "x,y"]],
            )
        self.assertEqual(input_path.read_bytes(), input_bytes)


if __name__ == "__main__":
    unittest.main()

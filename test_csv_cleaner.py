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
* invalid inputs (zero-byte file, BOM-only file, empty and duplicate
  header column names, an unterminated quoted field, invalid UTF-8 bytes
  and a record with too many fields following a record containing a
  quoted newline) fail with exit code 2, empty stdout and a categorized
  reason on stderr without a Python traceback; no output file is left
  behind, even when an earlier record could already have been cleaned,
  and the input bytes stay untouched.
* output path protection: for each rule, an output path that already
  names a regular file is refused whether that file holds valid CSV or
  non-UTF-8 bytes, and both the target and the legal input stay
  byte-for-byte intact; an output path that names the input file itself,
  given verbatim or via a different spelling containing a "." segment,
  is refused without deleting or rewriting the input. Every refusal
  exits 2 with empty stdout, the documented reason on stderr, no Python
  traceback and no extra cleaned file. A single-row trim run to a
  brand-new path serves as the success control.
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

    def assert_refusal(self, result, *, reason_fragment):
        """Common assertions for a documented output-path refusal.

        Exit code 2, empty stdout, the given reason fragment on stderr,
        and no Python traceback. File-preservation assertions stay with
        the individual cases, which know which bytes to compare.
        """
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        stderr_text = result.stderr.decode("utf-8", errors="replace")
        self.assertIn(reason_fragment, stderr_text)
        # The refusal must come through the documented error path rather
        # than an uncaught exception.
        self.assertNotIn("Traceback", stderr_text)
        self.assertNotIn("Error:", stderr_text)
        return stderr_text

    def test_existing_output_file_is_refused_for_trim_and_normalize_null(self):
        # An already-present regular file at the output path blocks the
        # export before the input is ever read: exit 2, empty stdout, the
        # documented reason on stderr, and both files byte-for-byte as
        # they were. The input stays a legal CSV with the named column
        # present and one cleanable value, so path protection -- not an
        # input error -- is what fails the run. The target is checked as
        # valid CSV and as raw non-UTF-8 bytes.
        existing_targets = [
            ("valid_csv",
             encode_csv([["keep", "me"], ["unchanged", "data"]], bom=False)),
            ("non_utf8", b"keep,\xff\n"),
        ]
        cases = [
            ("trim", [HEADER, [" Alice ", "x,y"]]),
            ("normalize-null", [HEADER, [" NULL ", "plain"]]),
        ]
        for rule, rows in cases:
            for target_tag, target_bytes in existing_targets:
                with self.subTest(rule=rule, target=target_tag):
                    input_path, input_bytes = self.write_input(
                        rows, bom=False,
                        tag=f"exists_in_{rule.replace('-', '_')}_{target_tag}",
                    )
                    output_path = self.tmpdir / (
                        f"existing_{rule.replace('-', '_')}_{target_tag}.csv"
                    )
                    output_path.write_bytes(target_bytes)
                    before = sorted(p.name for p in self.tmpdir.iterdir())

                    result = self.run_cleaner(
                        input_path, output_path, rule=rule
                    )

                    self.assert_refusal(
                        result, reason_fragment="output file already exists"
                    )
                    # The existing target survives with its exact bytes,
                    # even when those bytes are not valid UTF-8...
                    self.assertEqual(
                        output_path.read_bytes(), target_bytes
                    )
                    # ...and the legal input is never rewritten.
                    self.assertEqual(input_path.read_bytes(), input_bytes)
                    # No extra cleaned file appears in the temp directory.
                    self.assertEqual(
                        sorted(p.name for p in self.tmpdir.iterdir()),
                        before,
                    )

    def test_output_equal_to_input_path_is_refused_for_both_rules(self):
        # Same string for --input and --output must be refused without
        # touching the input. Each rule gets a legal CSV whose named
        # column holds a value the rule would clean.
        cases = [
            ("trim", [HEADER, [" Alice ", "x,y"]]),
            ("normalize-null", [HEADER, [" N/A ", "plain"]]),
        ]
        for rule, rows in cases:
            with self.subTest(rule=rule):
                input_path, input_bytes = self.write_input(
                    rows, bom=False, tag=f"same_path_{rule.replace('-', '_')}"
                )
                before = sorted(p.name for p in self.tmpdir.iterdir())

                result = self.run_cleaner(
                    input_path, input_path, rule=rule
                )

                self.assert_refusal(
                    result,
                    reason_fragment="output path must be different from the "
                                    "input path",
                )
                self.assertTrue(input_path.exists())
                self.assertEqual(input_path.read_bytes(), input_bytes)
                self.assertEqual(
                    sorted(p.name for p in self.tmpdir.iterdir()),
                    before,
                )

    def test_dot_segment_spelling_of_input_path_is_refused_for_both_rules(
        self,
    ):
        # --output spelled differently but resolving to the same file
        # (a redundant "." path segment) must be recognized as the same
        # path and refused; the input must not be deleted or rewritten.
        cases = [
            ("trim", [HEADER, [" Alice ", "x,y"]]),
            ("normalize-null", [HEADER, ["null", "plain"]]),
        ]
        for rule, rows in cases:
            with self.subTest(rule=rule):
                input_path, input_bytes = self.write_input(
                    rows, bom=False,
                    tag=f"dot_segment_in_{rule.replace('-', '_')}",
                )
                # A genuinely different spelling: same resolved file, with
                # a "." segment the input spelling does not have. Build it
                # as a raw string so pathlib does not collapse it for us.
                alternate = os.path.join(
                    str(input_path.parent), ".", input_path.name
                )
                self.assertNotEqual(alternate, str(input_path))
                self.assertEqual(
                    os.path.abspath(alternate),
                    os.path.abspath(str(input_path)),
                )
                before = sorted(p.name for p in self.tmpdir.iterdir())

                result = self.run_cleaner(
                    input_path, alternate, rule=rule
                )

                self.assert_refusal(
                    result,
                    reason_fragment="output path must be different from the "
                                    "input path",
                )
                self.assertTrue(input_path.exists())
                self.assertEqual(input_path.read_bytes(), input_bytes)
                self.assertEqual(
                    sorted(p.name for p in self.tmpdir.iterdir()),
                    before,
                )

    def test_trim_single_row_exports_to_new_path(self):
        # Success control for the output-path protection cases: a legal
        # single-record input exported to a path that does not yet exist
        # exits 0 with empty stderr, exactly one JSON summary object on
        # stdout, a BOM-free UTF-8 output whose parsed values are the
        # trimmed results, and untouched input bytes.
        input_path, original_bytes = self.write_input(
            [HEADER, [" Alice ", "x,y"]], bom=False, tag="single"
        )
        output_path = self.tmpdir / "cleaned.csv"
        self.assertFalse(output_path.exists())

        result = self.run_cleaner(input_path, output_path, rule="trim")

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        # stdout must consist of exactly the one JSON object and nothing
        # else; json.loads rejects trailing non-whitespace, and the
        # object must carry precisely the documented keys and values
        # regardless of key order.
        self.assertEqual(
            json.loads(result.stdout.decode("utf-8")),
            {"rows": 1, "changed_cells": 1},
        )

        self.assertTrue(output_path.exists())
        raw_output = output_path.read_bytes()
        raw_output.decode("utf-8")  # must be valid UTF-8...
        self.assertFalse(raw_output.startswith(codecs.BOM_UTF8))  # ...no BOM
        self.assertEqual(
            self.read_output_records(output_path),
            [HEADER, ["Alice", "x,y"]],
        )
        self.assertEqual(input_path.read_bytes(), original_bytes)


if __name__ == "__main__":
    unittest.main()

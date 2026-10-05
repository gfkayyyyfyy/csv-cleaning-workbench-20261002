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
  YYYY-MM-DD, DD/MM/YYYY, YYYY/MM/DD or YYYY.MM.DD (ASCII digits,
  zero-padded; the four spellings may be mixed in one column) normalize
  to YYYY-MM-DD, and the first invalid date (internal whitespace,
  unpadded numbers, mixed separators, time suffixes, fullwidth digits,
  NULL/N/A text, nonexistent calendar dates) fails by CSV record number
  without exporting anything. YYYY.MM.DD is always year-month-day with
  two English periods (its acceptance file is due_date,note with
  " 2024.02.29 ", 0001.01.01, 2024-03-01 and an empty cell: rows 4 /
  changed_cells 2, only records 2 and 3 listed); a non-leap
  2023.02.29 at record 3 fails the run and the --dry-run preview alike,
  leaving no output file behind.
  A year-boundary regression pins the documented 0001-9999 range: both
  endpoints convert (the low year keeps four digits, including the
  0001/01/01 slash spelling), 2000-02-29 is a century leap day in
  either spelling, and 1900-02-29, 29/02/2100, 0000-01-01 and
  01/01/10000 are each rejected at record 3 without partial output.
* normalize-date --date-order: the optional --date-order takes only the
  lowercase choices dmy and mdy and defaults to dmy when omitted, so the
  existing DD/MM/YYYY reading is unchanged. Under mdy a slash date with
  the four-digit year last is read as MM/DD/YYYY (05/06/2024 becomes
  2024-05-06) with ambiguous fields settled by the chosen order and no
  guessing or fallback: 13/02/2024 is month 13 and 02/30/2024 is
  February 30, both rejected at the first offending record number (the
  header is record 1, a quoted newline does not advance the number),
  while the same 13/02/2024 is a clean 2024-02-13 under dmy.
  YYYY-MM-DD, YYYY/MM/DD and YYYY.MM.DD stay year-month-day under
  either order (a year-last dot value such as 03.02.2024 is rejected
  under both), blank cells stay empty, the summary keeps its two-key
  shape and the --include-changes entries list the raw before value
  and the order's after value in record order. A missing or non-choice
  --date-order value (DMY, ymd), or an explicit order paired with trim /
  normalize-null, fails with exit code 2, empty stdout, the option and
  reason on stderr, no Python traceback and no output file -- including
  for a header-only input; a valid order on a header-only input exports
  just the header with both counts at 0.
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
* --null-replacement: the optional replacement text for normalize-null
  is written verbatim into every cell the rule would otherwise turn
  into an empty string (blank or whitespace-only values, the default
  NULL / N/A markers and any --null-marker additions), without
  stripping, case-folding or re-matching against the markers; empty and
  whitespace-only replacements are allowed, and omitting the option
  keeps the default empty-string behavior. The acceptance sample (names
  " NULL ", 待补, 未知, " Bob " with marker 待补 and replacement 未知)
  reports rows 4 / changed_cells 2 with only records 2 and 3 listed
  under --include-changes (a cell whose original value already equals
  the replacement is not a change), identically under --dry-run (which
  creates nothing) and a real BOM-free export. A missing replacement
  value, or pairing the option with trim / normalize-date /
  normalize-whitespace, fails with exit code 2, empty stdout, the
  option and reason on stderr, no Python traceback and no output file
  -- including for a header-only input; a header-only input with a
  valid replacement exports just the header with both counts at 0 and
  an empty changes array.
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
* local file access failures: a genuinely missing input file and an
  output path whose parent directory does not exist each fail with exit
  code 2, empty stdout and the categorized reason on stderr (no Python
  traceback), both with and without --include-changes (so no summary or
  changes detail is ever printed). The missing input is not created, no
  output file or missing parent directory is created, and the input
  bytes stay unchanged. Both cases run through the public CLI against
  real absent paths inside private temporary directories, without
  relying on permission settings, disk capacity or fixed absolute
  paths, so they reproduce on Windows and common Unix-like systems.
* --dry-run preview: the input is fully read and validated and the same
  summary JSON is printed (with and without --include-changes), but no
  output file, missing parent directory or other new file is created and
  the input bytes stay untouched. The trim sample has the name,note
  header and four records whose names are " Alice ", "Bob", three
  spaces and an already-empty string, while the notes carry a comma,
  double quotes and a quoted real newline; the preview reports rows 4 /
  changed_cells 2, and with details only records 2 and 4 (the header is
  record 1) appear with their original whitespace preserved as
  before and "Alice" / "" as after, proving record numbers ignore the
  embedded newline. A real export of the same input prints the identical
  summary and writes the trimmed name column with the note column
  verbatim; a preview whose output parent does not exist still succeeds
  without creating that directory; a header-only preview reports both
  counts at 0 and an empty changes array. Preview also keeps every
  existing failure boundary: a one-field record 4 following a legal
  quoted-newline record fails with exit code 2, empty stdout and the
  "record 4 ... 1 field(s) ... expected 2" diagnostic even with
  --include-changes, and an existing output file or an output path equal
  to the input path is rejected with the documented wording, no Python
  traceback, no new files and byte-for-byte unchanged input and target
  files -- so --dry-run skips only the write step, never validation or
  path protection.
* --dry-run preview of normalize-date: the due_date,note sample has four
  records whose dates are " 29/02/2024 ", "2024-03-01", three spaces
  and an empty string, with a quoted real newline inside the second
  record's note. The preview exits 0 with empty stderr and a single
  JSON object (rows 4, changed_cells 2) with and without
  --include-changes; only records 2 and 4 are listed, with the
  original whitespace in before and "2024-02-29" / "" after, and no
  output file or other new file appears. A real export of the same
  input prints the identical summary under each switch setting and
  writes 2024-02-29 / 2024-03-01 / "" / "" with the note column,
  header and record order preserved, while the preview path stays
  absent. With 31/02/2024 at record 4 and NULL at record 5 the
  preview fails with exit code 2, empty stdout and the first invalid
  due_date value reported at record 4 (no Python traceback, no
  summary or changes detail, no output file), and the input bytes
  stay unchanged throughout.
* --dry-run preview of normalize-null combined with --null-marker: the
  BOM-prefixed UTF-8 sample has the name,note header and seven records
  whose names are " MISSING ", " n/A ", three plain spaces, an empty
  string, " NULLABLE ", " Ä " and "NuLl", with a quoted real newline in
  the second record's note and commas, double quotes and plain text
  across the other notes. The four custom markers MISSING, missing,
  " n/A " and "ä" collapse to two effective keys (duplicate markers
  never inflate the count). The preview exits 0 with empty stderr and a
  single JSON object (rows 7, changed_cells 4); without
  --include-changes there is no changes key, with it only records 2, 3,
  4 and 8 appear in order (the header is record 1 and the quoted
  newline does not advance the number), before keeping the original
  values and after always "". The two unmatched values keep their
  surrounding whitespace. The preview output path sits inside a
  nonexistent parent directory and neither the file nor the directory
  is created. A real export of the same input prints the identical
  summary under each detail setting (compared by content, not key
  order) and writes a BOM-free file with the expected name column and
  the header, record order and note values preserved. A header-only
  input with valid markers previews with both counts at 0 and an empty
  changes array; a whitespace-only marker fails even on a header-only
  input with exit code 2, empty stdout, the --null-marker / non-empty
  reason on stderr, no Python traceback and no new files. The input
  bytes stay unchanged throughout.
* --dry-run preview combined with --date-order: the due_date,note
  sample has four records whose dates are 05/06/2024, 2024/02/29,
  2024-01-01 and an empty string, with a quoted real newline inside the
  first record's note. Under mdy the preview's first two normalized
  results are 2024-05-06 / 2024-02-29; under explicit dmy and with the
  option omitted (the documented default) they are 2024-06-05 /
  2024-02-29. All three exit 0 with empty stderr and rows 4 /
  changed_cells 2, with and without --include-changes: without the
  switch there is no changes key, with it only records 2 and 3 are
  listed in record order, naming due_date with the exact raw before
  value and the chosen order's after value. A real export to a separate
  fresh path prints the same JSON content (compared by parsed content,
  not key order) and preserves the header, every note and the record
  order with the order's normalized dates; the preview path stays
  absent even below a nonexistent parent directory, which is not
  created. A second file (05/06/2024 with the quoted-newline note, then
  13/02/2024 and 02/30/2024) fails the mdy preview with exit 2, empty
  stdout and a single diagnostic locating due_date at record 3 with
  the raw value 13/02/2024 -- no Python traceback and no later record
  reported -- with and without the details switch, proving the chosen
  order never bypasses date validation. The input bytes stay unchanged
  and no output or extra file appears in any preview.
* normalize-whitespace: the name,note acceptance sample has four records
  whose names parse as " Alice  Smith ", a string holding only a tab and
  an ideographic space, "Bob Lee" and an empty string, with a quoted
  real newline inside the first record's note. The cleaned names are
  "Alice Smith", "", "Bob Lee" and ""; the summary reports rows 4 /
  changed_cells 2, and with --include-changes only records 2 and 3
  appear in record order with the original values in before. NULL, N/A
  and date text are only whitespace-normalized, never converted, and
  whitespace-only cells become empty while U+200B zero-width spaces are
  preserved. A --dry-run preview prints the identical summary without
  creating the output file or its missing parent directory; a
  header-only input reports both counts at 0 and an empty changes array.
  Pairing the rule with --null-marker or --date-order fails with exit
  code 2, empty stdout and the incompatible-option reason on stderr,
  with no output file -- including for a header-only input.
* command-line argument validation: one legal UTF-8 sample (header
  name,note, a single record whose name parses as " Alice " and whose
  note parses as "x,y") isolates the argument errors. Removing any one
  of --input, --output, --column or --rule from an otherwise valid
  call, or naming a rule the tool does not support ("unknown-rule", or
  "Trim" with a capital T, since rule names are case-sensitive), fails
  with exit code 2, a byte-for-byte empty stdout (checked for the
  unknown rules with and without --include-changes, so neither the
  summary nor a changes array is ever printed), the omitted option
  name or the unsupported-rule reason with the passed value on stderr,
  and no Python traceback. The input bytes stay unchanged, the
  designated output never appears (with --output omitted no implicit
  output is generated either) and the temporary directory gains no new
  files. A valid trim call with --include-changes on the same input is
  the success control: exit 0, empty stderr, rows and changed_cells
  both 1, a changes array holding only record 2 (the header is record
  1) with name changing from " Alice " to "Alice", and a BOM-free
  UTF-8 export whose header and note value are preserved while the
  input stays byte-for-byte untouched.
* empty physical lines and empty fields at the CSV record boundary: all
  runs use trim on the name column with --include-changes. With the
  name,note header, a record 2 whose name parses as " Alice " and whose
  quoted note is two-line text with a real newline, a completely empty
  physical line before the trailing Bob,z record parses as record 3
  with zero fields, so both the export and the --dry-run preview fail
  with exit code 2, empty stdout and the "record 3 ... 0 field(s) ...
  expected 2" diagnostic, leaving no cleaned Alice, no output file and
  no other new file behind. A file whose very first physical line is
  empty fails both modes with exit code 2, empty stdout and the
  "input is empty ... no header record" diagnostic even though a normal
  header follows. The success control keeps the same header with three
  records: a name " Alice " whose quoted note holds two consecutive
  real newlines (the blank physical line belongs to the note), a bare
  comma meaning two empty fields, and Bob,z -- none of them rejected
  or skipped. Both modes exit 0 with empty stderr and rows 3 /
  changed_cells 1, the changes array listing only record 2 with name
  " Alice " -> "Alice"; the export preserves all three records and the
  note's real newlines as BOM-free UTF-8, and the preview prints the
  identical JSON content without creating the output file or its
  missing parent directory. Every sample runs with LF and CRLF record
  separators and with and without a UTF-8 BOM, comparing parsed fields
  and JSON content rather than equivalent quoting styles or JSON key
  order, and the input bytes stay byte-for-byte unchanged.
* --delimiter semicolon: the explicit field delimiter is used for both
  reading and exporting and is never guessed from the file. The
  name,note acceptance sample has three records whose names parse as
  " Alice ", three ASCII spaces and Bob, while the notes parse as
  'x;y"z' plus a real newline and 'next', ok and z; the first note
  embeds a semicolon, a double quote and a quoted real newline. A trim
  run with --delimiter semicolon and --include-changes is exercised
  with and without a UTF-8 BOM: exit 0, empty stderr and a single JSON
  object reporting rows 3 / changed_cells 2, with changes listing only
  records 2 and 3 in order, each on column name, before keeping the
  original whitespace and after being "Alice" and the empty string.
  The export is BOM-free UTF-8 written with semicolons, so reading it
  back with the semicolon dialect restores the header, record order
  and every note value unchanged, and the input bytes stay untouched.
  A --dry-run of the same input prints the identical JSON content and,
  with the output below a nonexistent parent directory, creates
  neither the directory nor the file. The delimiter is never sniffed:
  on a file holding just name;note and Bob;z, omitting --delimiter
  (the documented comma default) fails with exit code 2, empty stdout,
  a "column not found" reason naming name, no output file and
  untouched input bytes. --delimiter with no following value, with an
  empty string or with the capitalized "Semicolon" fails with exit
  code 2, empty stdout, a stderr reason naming --delimiter and the
  missing or illegal value, no output file and untouched input bytes,
  both on the two-record data file and on a header-only file.
  Omitting the option on a comma-separated file keeps the default
  comma entry point's original behavior.
* --delimiter tab: the tab-separated name,note acceptance sample has
  four records whose names parse as " Alice ", Bob, three ASCII
  spaces and an empty string, while the first note parses as
  'x\ty"z\nnext' (a literal tab, a double quote and a quoted real
  newline inside the field) and the other notes are ok, z and end.
  A trim run with --delimiter tab is exercised with and without a
  UTF-8 BOM: exit 0, empty stderr and a single JSON object reporting
  rows 4 / changed_cells 2; with --include-changes only records 2
  and 4 are listed in order, each on column name, before keeping the
  original whitespace and after being "Alice" and the empty string,
  and without the switch there is no changes key. The export is
  BOM-free UTF-8 written with real tabs, so reading it back with the
  tab dialect restores the header, record order and every note value
  unchanged, and the input bytes stay untouched. A --dry-run of the
  same input prints the identical JSON content and, with the output
  below a nonexistent parent directory, creates neither the
  directory nor the file. Replacing the third data record with a
  name-only record (the first note keeps its quoted newline, so the
  short record is CSV record 4) fails both the export and the
  preview with exit code 2, empty stdout and the "record 4 ... 1
  field(s) ... expected 2" diagnostic, no Python traceback, no
  output file and untouched input bytes.
* --output-delimiter: the export delimiter is chosen independently of
  the input delimiter. The name,note acceptance sample is written with
  semicolons and has three records whose names parse as " Alice ", Bob
  and three ASCII spaces, while the first note parses as 'x;y,z"q' plus
  a real newline and 'next' (a semicolon, a comma, a double quote and a
  quoted real newline inside one field) and the other notes are ok and
  end. A trim run with --delimiter semicolon and --output-delimiter
  comma is exercised with and without a UTF-8 BOM: exit 0, empty
  stderr, a BOM-free UTF-8 export that reads back under the comma
  dialect with the header, record order and every note value unchanged,
  and a summary reporting rows 3 / changed_cells 2 where the delimiter
  conversion itself never counts as a change; with --include-changes
  only records 2 and 4 are listed in order, each on column name, before
  keeping the original whitespace and after being "Alice" and the empty
  string, and without the switch there is no changes key. The same
  sample exported with --output-delimiter tab reads back under the tab
  dialect, and omitting --output-delimiter keeps the export on the
  input delimiter (semicolon). A --dry-run of the same input prints the
  identical JSON content and, with the output below a nonexistent
  parent directory, creates neither the directory nor the file.
  --output-delimiter with no following value, with an empty string or
  with the capitalized "Comma" fails with exit code 2, empty stdout, a
  stderr reason naming --output-delimiter and the missing or illegal
  value, no Python traceback, no output file and untouched input bytes,
  both on the data sample and on a header-only file.
* normalize-null text fidelity across a semicolon-to-comma delimiter
  conversion: a UTF-8 semicolon name;note sample whose three parsed data
  rows are (" NULL ", a;b), (待补, "line one\nline two") and
  (" Bob ", ok) is run with --delimiter semicolon, --output-delimiter
  comma, --null-marker 待补, --null-replacement set to
  ' 未知,待补;"待定"\n下一行 ' (one space at each end, a comma, a
  semicolon, double quotes and a real newline inside) and
  --include-changes, both with and without a UTF-8 BOM. The --dry-run
  preview (into a path below a nonexistent parent directory) and the
  real export into an existing directory both exit 0 with empty stderr
  and print the same single parsed JSON object: rows 3 /
  changed_cells 2, with only records 2 and 3 listed in record order on
  column name, before being " NULL " and 待补 and after being the full
  replacement text. The BOM-free UTF-8 comma export reads back with
  exactly two fields per record: the header, record order and every
  note stay unchanged (including the quoted real newline) and the
  third name " Bob " keeps both surrounding spaces; the preview
  creates neither the file nor the missing parent and the input bytes
  stay untouched. A variant whose third data record has only one
  field fails in both preview and export with exit 2, empty stdout and
  stderr exactly "error: record 4 has 1 field(s), expected 2\n" (the
  real newline quoted inside the preceding note does not advance the
  record number), no Python traceback, no output file and untouched
  input bytes.
* --include-null-matches: the normalize-null hit detail is reported
  independently of whether the replacement actually changes a cell.
  The comma state,note acceptance sample has five data records whose
  states parse as "", " NULL ", missing, N/A and NULLABLE; the first
  note carries a quoted real newline and the other four notes are ok.
  With --null-marker MISSING, --null-replacement missing and both
  detail switches, the --dry-run preview (output below a nonexistent
  parent directory) and a real export both exit 0 with empty stderr and
  print the same parsed JSON: rows 5 / changed_cells 3, null_matches
  listing records 2, 3, 4 and 5 in record order on column state with
  only record/column/before and the parsed originals "", " NULL ",
  missing and N/A (record numbers count the header as 1 and do not
  advance for the quoted newline), while changes lists only records 2,
  3 and 5 -- record 4 already spells the replacement, so it matches
  without being a change -- each with after missing. The BOM-free export
  keeps the header, record order and every note value, writes missing
  into the first four states and keeps NULLABLE verbatim; the preview
  creates neither the output file nor its missing parent directory and
  the input bytes stay untouched both times. Omitting
  --include-null-matches leaves the null_matches key out of the JSON
  (with and without --include-changes), enabling only the hit detail
  leaves changes out, and every switch combination reports the same
  counts and writes byte-identical CSV. A header-only input with both
  switches reports 0/0 and two empty arrays, exporting just the header.
  Pairing --include-null-matches with trim, even on a header-only input,
  exits 2 with empty stdout and the reason that the switch can only be
  used with --rule normalize-null, no Python traceback, no output file
  and untouched input bytes.
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

# Mixed-spelling sample mirroring the documented YYYY/MM/DD acceptance
# file: a padded YYYY/MM/DD leap day, DD/MM/YYYY and already-ISO dates
# in one column, plus a whitespace-only cell; the note column carries the
# quoting hazards and must round-trip untouched.
MIXED_DATE_ROWS = [
    DATE_HEADER,
    [" 2024/02/29 ", "x,y"],              # YYYY/MM/DD, padded ends
    ["01/03/2024", "ok"],                 # DD/MM/YYYY -> 2024-03-01
    ["2024-03-02", "z"],                  # already ISO: not a change
    ["   ", "blank"],                     # whitespace-only -> empty
]
MIXED_DATE_EXPECTED_DATES = [
    "2024-02-29", "2024-03-01", "2024-03-02", "",
]
# Rows 1, 2 and 4 change; row 3 was already ISO.
MIXED_DATE_EXPECTED_CHANGED = 3
MIXED_DATE_EXPECTED_CHANGES_DETAIL = [
    {"record": 2, "column": "due_date",
     "before": " 2024/02/29 ", "after": "2024-02-29"},
    {"record": 3, "column": "due_date",
     "before": "01/03/2024", "after": "2024-03-01"},
    {"record": 5, "column": "due_date",
     "before": "   ", "after": ""},
]

# Dot-spelling sample mirroring the acceptance dates.csv: the new
# YYYY.MM.DD spelling is mixed with an already-ISO date and an empty
# cell. The first value is padded at both ends; only records 2 and 3
# change (record 4 is already ISO and record 5 already empty).
DOT_DATE_ROWS = [
    DATE_HEADER,
    [" 2024.02.29 ", "a"],          # YYYY.MM.DD, padded ends -> 2024-02-29
    ["0001.01.01", "b"],            # year 0001 endpoint -> 0001-01-01
    ["2024-03-01", "c"],            # already ISO: not a change
    ["", "d"],                      # already empty: not a change
]
DOT_DATE_EXPECTED_DATES = [
    "2024-02-29", "0001-01-01", "2024-03-01", "",
]
DOT_DATE_EXPECTED_CHANGED = 2
DOT_DATE_EXPECTED_CHANGES_DETAIL = [
    {"record": 2, "column": "due_date",
     "before": " 2024.02.29 ", "after": "2024-02-29"},
    {"record": 3, "column": "due_date",
     "before": "0001.01.01", "after": "0001-01-01"},
]

# Same sample with record 3's dot date changed to the non-leap
# 2023.02.29: the run must abort at record 3 (the header is record 1)
# and never reach the later records, leaving no output file behind.
DOT_INVALID_ROWS = [
    DATE_HEADER,
    [" 2024.02.29 ", "a"],
    ["2023.02.29", "b"],
    ["2024-03-01", "c"],
    ["", "d"],
]

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
    "01-03-2024",        # dashes only in YYYY-MM-DD order
    # YYYY/MM/DD spelling: same strictness as the other two.
    "2024/2/29",         # unpadded month
    "2024/02/30",        # February never has 30 days
    "0000/01/01",        # year 0000 is outside 0001-9999
    "２０２４/０２/２９",   # fullwidth digits are not ASCII digits
    "2024/02/29 10:30",  # time suffix
    "2024 /02/29",       # internal whitespace
    "2024/02/29/x",      # trailing component
    "2024/02",           # missing day
    # YYYY.MM.DD spelling: same strictness, two English periods only,
    # always year-month-day and independent of --date-order.
    "2023.02.29",        # 2023 is not a leap year
    "2024.2.29",         # unpadded month
    "2024.02.1",         # unpadded day
    "0000.01.01",        # year 0000 is outside 0001-9999
    "２０２４.０２.２９",   # fullwidth digits are not ASCII digits
    "2024.02.29 10:30",  # time suffix
    "2024 .02.29",       # internal whitespace
    "2024.02.29/x",      # trailing component
    "2024.02",           # missing day
    "01.02.2024",        # dots are only accepted as YYYY.MM.DD, year first
    "2024-02.29",        # mixed separator: dash then dot
    "2024/02.29",        # mixed separator: slash then dot
    "2024.02-29",        # mixed separator: dot then dash
    "2024。02。29",        # ideographic full stop, not an English period
    "2024.13.01",        # month 13 does not exist
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
    "1900.02.29",   # same non-leap century in the YYYY.MM.DD spelling
    "10000.01.01",  # a five-digit dot year is one above the range
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


def encode_lines(lines, *, newline, bom):
    """Join physical lines with the given record separator, as bytes.

    Unlike encode_csv this keeps exact control of the physical layout:
    an element may be a completely empty line or hold quoted newlines,
    which the empty-line boundary samples need.
    """
    data = (newline.join(lines) + newline).encode("utf-8")
    if bom:
        data = codecs.BOM_UTF8 + data
    return data


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
                    column="name", include_changes=False):
        argv = [
            sys.executable,
            str(SCRIPT_PATH),
            "--input", str(input_path),
            "--output", str(output_path),
            "--column", column,
            "--rule", rule,
        ]
        if include_changes:
            argv.append("--include-changes")
        return subprocess.run(
            argv,
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

    def test_normalize_date_mixed_spellings_in_one_column(self):
        # The documented YYYY/MM/DD acceptance file: the three spellings
        # are mixed in due_date (with a whitespace-only cell), so the
        # run must exit 0 with rows 4 / changed_cells 3 and write
        # 2024-02-29 / 2024-03-01 / 2024-03-02 / "" while leaving the
        # header, record order and parsed note text untouched.
        input_path, original_bytes = self.write_input(
            MIXED_DATE_ROWS, bom=False, tag="date_mixed"
        )
        output_path = self.tmpdir / "cleaned_date_mixed.csv"
        self.assertFalse(output_path.exists())

        result = self.run_cleaner(
            input_path, output_path,
            rule="normalize-date", column="due_date",
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(
            json.loads(result.stdout.decode("utf-8")),
            {"rows": 4, "changed_cells": MIXED_DATE_EXPECTED_CHANGED},
        )

        output_rows = self.read_output_records(output_path)
        self.assertEqual(output_rows[0], DATE_HEADER)
        self.assertEqual(len(output_rows), 5)
        self.assertEqual(
            [row[0] for row in output_rows[1:]],
            MIXED_DATE_EXPECTED_DATES,
        )
        self.assertEqual(
            [row[1] for row in output_rows],
            [row[1] for row in MIXED_DATE_ROWS],
        )
        self.assertEqual(input_path.read_bytes(), original_bytes)

    def test_normalize_date_mixed_spellings_changes_detail(self):
        # With --include-changes only records 2, 3 and 5 are listed in
        # record order; before keeps the parsed original value (including
        # the surrounding spaces) and after holds the conversion result.
        input_path, _ = self.write_input(
            MIXED_DATE_ROWS, bom=False, tag="date_mixed_changes"
        )
        output_path = self.tmpdir / "cleaned_date_mixed_changes.csv"

        result = self.run_cleaner(
            input_path, output_path,
            rule="normalize-date", column="due_date",
            include_changes=True,
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        summary = json.loads(result.stdout.decode("utf-8"))
        self.assertEqual(summary["rows"], 4)
        self.assertEqual(
            summary["changed_cells"], MIXED_DATE_EXPECTED_CHANGED
        )
        self.assertEqual(
            summary["changes"], MIXED_DATE_EXPECTED_CHANGES_DETAIL
        )

    def test_normalize_date_ymd_slash_year_endpoint(self):
        # The 0001/01/01 spelling converts to 0001-01-01 and keeps four
        # digits through the ISO output; padded ends are stripped first.
        rows = [
            DATE_HEADER,
            [" 0001/01/01 ", "x,y"],
            ["9999/12/31", "end"],
        ]
        input_path, original_bytes = self.write_input(
            rows, bom=False, tag="date_ymd_slash_endpoints"
        )
        output_path = self.tmpdir / "cleaned_date_ymd_slash_endpoints.csv"

        result = self.run_cleaner(
            input_path, output_path,
            rule="normalize-date", column="due_date",
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(
            json.loads(result.stdout.decode("utf-8")),
            {"rows": 2, "changed_cells": 2},
        )
        self.assertEqual(
            [row[0] for row in self.read_output_records(output_path)[1:]],
            ["0001-01-01", "9999-12-31"],
        )
        self.assertEqual(input_path.read_bytes(), original_bytes)

    def test_normalize_date_dot_spelling_acceptance(self):
        # The documented YYYY.MM.DD acceptance file: a padded dot leap
        # day at record 2 and 0001.01.01 at record 3 change, the
        # already-ISO record 4 and empty record 5 do not. The run exits
        # 0 with rows 4 / changed_cells 2, the header, record order and
        # parsed note text are untouched, and the export is BOM-free
        # even when the input carries a BOM.
        for bom in (False, True):
            with self.subTest(bom=bom):
                tag = "date_dot_bom" if bom else "date_dot_nobom"
                input_path, original_bytes = self.write_input(
                    DOT_DATE_ROWS, bom=bom, tag=tag
                )
                output_path = self.tmpdir / f"cleaned_{tag}.csv"
                self.assertFalse(output_path.exists())

                result = self.run_cleaner(
                    input_path, output_path,
                    rule="normalize-date", column="due_date",
                )

                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, b"")
                self.assertEqual(
                    json.loads(result.stdout.decode("utf-8")),
                    {"rows": 4,
                     "changed_cells": DOT_DATE_EXPECTED_CHANGED},
                )

                self.assertTrue(output_path.exists())
                self.assertFalse(
                    output_path.read_bytes().startswith(codecs.BOM_UTF8)
                )
                output_rows = self.read_output_records(output_path)
                self.assertEqual(output_rows[0], DATE_HEADER)
                self.assertEqual(len(output_rows), 5)
                self.assertEqual(
                    [row[0] for row in output_rows[1:]],
                    DOT_DATE_EXPECTED_DATES,
                )
                self.assertEqual(
                    [row[1] for row in output_rows],
                    [row[1] for row in DOT_DATE_ROWS],
                )
                self.assertEqual(input_path.read_bytes(), original_bytes)

    def test_normalize_date_dot_spelling_changes_detail(self):
        # With --include-changes only records 2 and 3 are listed in
        # record order; before keeps the parsed original value (spaces
        # and all) and after holds the converted ISO date.
        input_path, _ = self.write_input(
            DOT_DATE_ROWS, bom=False, tag="date_dot_changes"
        )
        output_path = self.tmpdir / "cleaned_date_dot_changes.csv"

        result = self.run_cleaner(
            input_path, output_path,
            rule="normalize-date", column="due_date",
            include_changes=True,
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        summary = json.loads(result.stdout.decode("utf-8"))
        self.assertEqual(summary["rows"], 4)
        self.assertEqual(
            summary["changed_cells"], DOT_DATE_EXPECTED_CHANGED
        )
        self.assertEqual(
            summary["changes"], DOT_DATE_EXPECTED_CHANGES_DETAIL
        )

    def test_normalize_date_dot_year_endpoints(self):
        # The 0001.01.01 spelling converts to 0001-01-01 and keeps four
        # digits through the ISO output; 9999.12.31 is the upper
        # endpoint. Padded ends are stripped before matching.
        rows = [
            DATE_HEADER,
            [" 0001.01.01 ", "x,y"],
            ["9999.12.31", "end"],
        ]
        input_path, original_bytes = self.write_input(
            rows, bom=False, tag="date_dot_endpoints"
        )
        output_path = self.tmpdir / "cleaned_date_dot_endpoints.csv"

        result = self.run_cleaner(
            input_path, output_path,
            rule="normalize-date", column="due_date",
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(
            json.loads(result.stdout.decode("utf-8")),
            {"rows": 2, "changed_cells": 2},
        )
        self.assertEqual(
            [row[0] for row in self.read_output_records(output_path)[1:]],
            ["0001-01-01", "9999-12-31"],
        )
        self.assertEqual(input_path.read_bytes(), original_bytes)

    def test_normalize_date_dot_non_leap_fails_by_record_number(self):
        # Record 3 carries the impossible 2023.02.29 (2023 is not a
        # leap year); it must be reported as record 3 with the original
        # value quoted, the later valid record 4 must not be exported
        # ahead of it, and no output file may be left behind.
        input_path, original_bytes = self.write_input(
            DOT_INVALID_ROWS, bom=False, tag="date_dot_invalid"
        )
        output_path = self.tmpdir / "cleaned_date_dot_invalid.csv"
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
        self.assertIn("2023.02.29", stderr_text)
        # Only the first invalid date is reported; the cleanable record
        # 2 and the records after the failure produce no output.
        self.assertNotIn("record 4", stderr_text)
        self.assertNotIn("record 5", stderr_text)
        self.assertNotIn("Traceback", stderr_text)
        self.assertFalse(output_path.exists())
        self.assertEqual(input_path.read_bytes(), original_bytes)

    def test_normalize_date_dot_mixes_with_all_other_spellings(self):
        # All four spellings plus a blank cell share one column: the
        # dot and slash values change, the already-ISO value does not,
        # and a whitespace-only cell becomes empty.
        rows = [
            DATE_HEADER,
            [" 2024.02.29 ", "dot"],            # -> 2024-02-29
            ["2024/03/05", "ymd slash"],        # -> 2024-03-05
            ["05/03/2024", "year-last slash"],  # dmy -> 2024-03-05
            ["2024-03-05", "already iso"],      # not a change
            ["  ", "blank"],                    # whitespace -> empty
        ]
        input_path, original_bytes = self.write_input(
            rows, bom=False, tag="date_dot_mixed"
        )
        output_path = self.tmpdir / "cleaned_date_dot_mixed.csv"

        result = self.run_cleaner(
            input_path, output_path,
            rule="normalize-date", column="due_date",
            include_changes=True,
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        summary = json.loads(result.stdout.decode("utf-8"))
        self.assertEqual(summary["rows"], 5)
        # Records 2, 3, 4 and 6 change; record 5 was already ISO.
        self.assertEqual(summary["changed_cells"], 4)
        self.assertEqual(
            [entry["record"] for entry in summary["changes"]],
            [2, 3, 4, 6],
        )
        self.assertEqual(
            [row[0] for row in self.read_output_records(output_path)[1:]],
            ["2024-02-29", "2024-03-05", "2024-03-05",
             "2024-03-05", ""],
        )
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


class NullReplacementCliTests(unittest.TestCase):
    """Coverage for the --null-replacement option of normalize-null.

    The option substitutes its verbatim text for every cell the rule
    would otherwise turn into an empty string. Every test goes through
    the public CLI with small CSV files prepared in a temporary
    directory; results are judged on parsed CSV fields and the parsed
    JSON object, so equivalent quoting styles and JSON key order are
    irrelevant.
    """

    # Acceptance sample: the name values are " NULL ", 待补, 未知 and
    # " Bob "; with the custom marker 待补 and the replacement 未知 the
    # first two names are substituted, the third already equals the
    # replacement text without matching a marker (not a change), and the
    # last is kept with its surrounding spaces.
    REPLACEMENT_ROWS = [
        HEADER,
        [" NULL ", "a"],
        ["待补", "b"],
        ["未知", "c"],
        [" Bob ", "d"],
    ]
    REPLACEMENT_EXPECTED_NAMES = ["未知", "未知", "未知", " Bob "]
    REPLACEMENT_EXPECTED_CHANGES = [
        {"record": 2, "column": "name", "before": " NULL ", "after": "未知"},
        {"record": 3, "column": "name", "before": "待补", "after": "未知"},
    ]

    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.tmpdir = Path(self._tempdir.name)

    def write_input(self, rows, *, bom, tag):
        data = encode_csv(rows, bom=bom)
        path = self.tmpdir / f"input_{tag}.csv"
        path.write_bytes(data)
        return path, data

    def run_cleaner(self, input_path, output_path, *, replacement,
                    rule="normalize-null", column="name",
                    markers=(), include_changes=False, dry_run=False):
        argv = [
            sys.executable,
            str(SCRIPT_PATH),
            "--input", str(input_path),
            "--output", str(output_path),
            "--column", column,
            "--rule", rule,
        ]
        for marker in markers:
            argv += ["--null-marker", marker]
        if replacement is not None:
            argv += ["--null-replacement", replacement]
        if include_changes:
            argv.append("--include-changes")
        if dry_run:
            argv.append("--dry-run")
        return subprocess.run(
            argv, cwd=str(self.tmpdir), capture_output=True
        )

    def read_output_records(self, path):
        # Plain utf-8 (not utf-8-sig) so a stray BOM would surface as content.
        with open(path, "r", encoding="utf-8", newline="") as outfile:
            return list(csv.reader(outfile))

    def test_replacement_dry_run_and_export_match_acceptance(self):
        for bom in (False, True):
            with self.subTest(bom=bom):
                tag = "repl_bom" if bom else "repl_nobom"
                input_path, original_bytes = self.write_input(
                    self.REPLACEMENT_ROWS, bom=bom, tag=tag
                )
                preview_path = self.tmpdir / f"preview_{tag}.csv"
                output_path = self.tmpdir / f"cleaned_{tag}.csv"

                preview = self.run_cleaner(
                    input_path, preview_path,
                    markers=["待补"], replacement="未知",
                    include_changes=True, dry_run=True,
                )

                self.assertEqual(preview.returncode, 0)
                self.assertEqual(preview.stderr, b"")
                self.assertEqual(
                    json.loads(preview.stdout.decode("utf-8")),
                    {"rows": 4, "changed_cells": 2,
                     "changes": self.REPLACEMENT_EXPECTED_CHANGES},
                )
                # The preview creates neither the file nor anything else.
                self.assertFalse(preview_path.exists())

                result = self.run_cleaner(
                    input_path, output_path,
                    markers=["待补"], replacement="未知",
                    include_changes=True,
                )

                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, b"")
                # The real export prints the identical summary.
                self.assertEqual(result.stdout, preview.stdout)

                raw_output = output_path.read_bytes()
                self.assertFalse(raw_output.startswith(codecs.BOM_UTF8))
                output_rows = self.read_output_records(output_path)
                self.assertEqual(output_rows[0], HEADER)
                self.assertEqual(
                    [row[0] for row in output_rows[1:]],
                    self.REPLACEMENT_EXPECTED_NAMES,
                )
                # The note column is never cleaned.
                self.assertEqual(
                    [row[1] for row in output_rows],
                    [row[1] for row in self.REPLACEMENT_ROWS],
                )
                self.assertEqual(input_path.read_bytes(), original_bytes)

    def test_replacement_is_verbatim_and_never_rematched(self):
        # A replacement that is itself a null marker is written as-is and
        # not re-normalized; surrounding whitespace and letter case in the
        # replacement survive untouched.
        input_path, original_bytes = self.write_input(
            [HEADER, [" n/A ", "x"], ["NULL", "y"], ["keep", "z"]],
            bom=False, tag="repl_verbatim",
        )
        output_path = self.tmpdir / "cleaned_repl_verbatim.csv"

        result = self.run_cleaner(
            input_path, output_path, replacement=" Null "
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(
            json.loads(result.stdout.decode("utf-8")),
            {"rows": 3, "changed_cells": 2},
        )
        self.assertEqual(
            [row[0] for row in self.read_output_records(output_path)[1:]],
            [" Null ", " Null ", "keep"],
        )
        self.assertEqual(input_path.read_bytes(), original_bytes)

    def test_empty_and_whitespace_only_replacements_are_allowed(self):
        # An empty replacement reproduces the default behavior; a
        # whitespace-only replacement is written verbatim. A cell whose
        # original value already equals the replacement is not a change.
        for replacement, expected_names, changed in (
            ("", ["", "keep"], 1),
            ("  ", ["  ", "keep"], 1),
            ("keep", ["keep", "keep"], 1),
        ):
            with self.subTest(replacement=replacement):
                tag = f"repl_edge_{changed}_{len(replacement)}"
                input_path, _ = self.write_input(
                    [HEADER, [" NULL ", "a"], ["keep", "b"]],
                    bom=False, tag=tag,
                )
                output_path = self.tmpdir / f"cleaned_{tag}.csv"

                result = self.run_cleaner(
                    input_path, output_path, replacement=replacement
                )

                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, b"")
                self.assertEqual(
                    json.loads(result.stdout.decode("utf-8")),
                    {"rows": 2, "changed_cells": changed},
                )
                self.assertEqual(
                    [row[0]
                     for row in self.read_output_records(output_path)[1:]],
                    expected_names,
                )

    def test_valid_replacement_header_only_file(self):
        input_path, original_bytes = self.write_input(
            [HEADER], bom=False, tag="repl_header_only"
        )
        output_path = self.tmpdir / "cleaned_repl_header_only.csv"

        result = self.run_cleaner(
            input_path, output_path,
            replacement="未知", include_changes=True,
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(
            json.loads(result.stdout.decode("utf-8")),
            {"rows": 0, "changed_cells": 0, "changes": []},
        )
        self.assertEqual(self.read_output_records(output_path), [HEADER])
        self.assertEqual(input_path.read_bytes(), original_bytes)

    # (label, replacement argv (None = option omitted entirely,
    # "MISSING" = bare flag with no value), rule, stderr fragments).
    INVALID_REPLACEMENT_SCENARIOS = [
        ("missing_value", "MISSING", "normalize-null",
         ["--null-replacement", "expected one argument"]),
        ("with_trim", "未知", "trim",
         ["--null-replacement can only be used with "
          "--rule normalize-null"]),
        ("with_normalize_date", "未知", "normalize-date",
         ["--null-replacement can only be used with "
          "--rule normalize-null"]),
        ("with_normalize_whitespace", "未知", "normalize-whitespace",
         ["--null-replacement can only be used with "
          "--rule normalize-null"]),
    ]

    def assert_invalid_replacement_rejected(self, rows, *, input_tag):
        input_path, original_bytes = self.write_input(
            rows, bom=False, tag=input_tag
        )
        scenarios = self.INVALID_REPLACEMENT_SCENARIOS
        for label, replacement, rule, fragments in scenarios:
            with self.subTest(label=label):
                output_path = self.tmpdir / f"cleaned_{input_tag}_{label}.csv"
                self.assertFalse(output_path.exists())

                argv = [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--input", str(input_path),
                    "--output", str(output_path),
                    "--column", "name",
                    "--rule", rule,
                    "--null-replacement",
                ]
                if replacement != "MISSING":
                    argv.append(replacement)
                result = subprocess.run(
                    argv, cwd=str(self.tmpdir), capture_output=True
                )

                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, b"")
                stderr_text = result.stderr.decode("utf-8")
                for fragment in fragments:
                    self.assertIn(fragment, stderr_text)
                self.assertNotIn("Traceback", stderr_text)
                self.assertFalse(output_path.exists())
                self.assertEqual(
                    input_path.read_bytes(), original_bytes
                )

    def test_invalid_replacement_rejected_on_data_file(self):
        self.assert_invalid_replacement_rejected(
            self.REPLACEMENT_ROWS, input_tag="repl_bad_data"
        )

    def test_invalid_replacement_rejected_on_header_only_file(self):
        # A perfectly valid header-only input must not make any of the
        # invalid parameter combinations acceptable.
        self.assert_invalid_replacement_rejected(
            [HEADER], input_tag="repl_bad_header"
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


class FileAccessFailureTests(unittest.TestCase):
    """Local file access failures promised by the README.

    Two scenarios are exercised end to end through the public CLI only,
    against real absent paths inside a private temporary directory:

    * the input file does not exist (its parent does);
    * the output file's parent directory does not exist.

    Both must fail with exit code 2, empty stdout and the categorized
    reason on stderr, without a Python traceback, with and without
    --include-changes (so neither a summary nor a changes detail may be
    printed), and without creating the missing input, any output file or
    the missing directory; a readable input keeps its exact bytes. The
    scenarios use ordinary missing paths rather than permission denial,
    disk-full conditions or fixed absolute paths, so they reproduce on
    Windows and common Unix-like systems with the standard library only.
    """

    # Valid UTF-8 CSV: documented header and one record whose name cell
    # the trim rule does change, so a write failure cannot be blamed on
    # there being nothing to clean.
    CLEANABLE_INPUT_BYTES = b'name,note\n" Alice ",ok\n'

    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.tmpdir = Path(self._tempdir.name)

    def make_workspace(self, label):
        """One fresh existing directory per (sub)test run."""
        workspace = self.tmpdir / label
        workspace.mkdir()
        return workspace

    def run_cleaner(self, input_path, output_path, *, include_changes):
        argv = [
            sys.executable,
            str(SCRIPT_PATH),
            "--input", str(input_path),
            "--output", str(output_path),
            "--column", "name",
            "--rule", "trim",
        ]
        if include_changes:
            argv.append("--include-changes")
        return subprocess.run(
            argv, cwd=str(self.tmpdir), capture_output=True
        )

    def assert_documented_failure(self, result, fragments):
        """Exit 2, empty stdout, each fragment on stderr, no traceback.

        Empty stdout is asserted byte-for-byte, which also proves that a
        failure prints neither the success summary nor a changes array.
        Only the fixed diagnostic fragments are constrained: the OS
        error number and its possibly localized explanation are not.
        """
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        stderr_text = result.stderr.decode("utf-8", errors="replace")
        for fragment in fragments:
            self.assertIn(fragment, stderr_text)
        self.assertNotIn("Traceback", stderr_text)

    def test_missing_input_file_fails_before_anything_is_created(self):
        # The input path names a genuinely absent file; the output goes
        # to an existing parent directory under a name that is free.
        for include_changes in (False, True):
            with self.subTest(include_changes=include_changes):
                label = "missing_input_with" if include_changes \
                    else "missing_input_without"
                workspace = self.make_workspace(label)
                input_path = workspace / "missing.csv"
                output_path = workspace / "cleaned.csv"
                # Pin the scenario preconditions explicitly.
                self.assertTrue(workspace.is_dir())
                self.assertFalse(input_path.exists())
                self.assertFalse(output_path.exists())

                result = self.run_cleaner(
                    input_path, output_path,
                    include_changes=include_changes,
                )

                self.assert_documented_failure(
                    result, ["cannot read input file", "missing.csv"]
                )
                # The missing input must not be created, the output file
                # must not appear, and nothing else may be left behind.
                self.assertFalse(input_path.exists())
                self.assertFalse(output_path.exists())
                self.assertEqual(list(workspace.iterdir()), [])

    def test_output_in_missing_directory_fails_without_creating_paths(self):
        # The input is a valid UTF-8 CSV holding a record the trim rule
        # would change; the output targets a free filename inside a
        # directory that does not exist.
        for include_changes in (False, True):
            with self.subTest(include_changes=include_changes):
                label = "missing_dir_with" if include_changes \
                    else "missing_dir_without"
                workspace = self.make_workspace(label)
                input_path = workspace / "input.csv"
                input_path.write_bytes(self.CLEANABLE_INPUT_BYTES)
                missing_dir = workspace / "nodir"
                output_path = missing_dir / "cleaned.csv"
                # Pin the scenario preconditions explicitly.
                self.assertFalse(missing_dir.exists())
                self.assertFalse(output_path.exists())

                result = self.run_cleaner(
                    input_path, output_path,
                    include_changes=include_changes,
                )

                self.assert_documented_failure(
                    result, ["cannot write output file", "cleaned.csv"]
                )
                # Neither the output file nor its missing parent
                # directory may be created...
                self.assertFalse(output_path.exists())
                self.assertFalse(missing_dir.exists())
                # ...the workspace contains only the untouched input...
                self.assertEqual(
                    sorted(p.name for p in workspace.iterdir()),
                    ["input.csv"],
                )
                # ...whose bytes remain exactly as they were written.
                self.assertEqual(
                    input_path.read_bytes(), self.CLEANABLE_INPUT_BYTES
                )

    def test_same_cleanable_input_exports_into_existing_directory(self):
        # Control for the write-failure scenario: the same valid input
        # succeeds when its output directory already exists, exporting
        # the header plus Alice,ok and the exact two-key summary, which
        # proves the failure above is caused by the missing directory
        # rather than by the input or arguments.
        workspace = self.make_workspace("missing_dir_control")
        input_path = workspace / "input.csv"
        input_path.write_bytes(self.CLEANABLE_INPUT_BYTES)
        output_path = workspace / "cleaned.csv"
        self.assertFalse(output_path.exists())

        result = self.run_cleaner(
            input_path, output_path, include_changes=False
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(
            json.loads(result.stdout.decode("utf-8")),
            {"rows": 1, "changed_cells": 1},
        )
        self.assertTrue(output_path.exists())
        self.assertFalse(
            output_path.read_bytes().startswith(codecs.BOM_UTF8)
        )
        self.assertEqual(
            self.read_output_records(output_path),
            [HEADER, ["Alice", "ok"]],
        )
        self.assertEqual(
            input_path.read_bytes(), self.CLEANABLE_INPUT_BYTES
        )

    def read_output_records(self, path):
        # Plain utf-8 (not utf-8-sig) so a stray BOM would surface as content.
        with open(path, "r", encoding="utf-8", newline="") as outfile:
            return list(csv.reader(outfile))


class IncludeChangesCliTests(unittest.TestCase):
    """Coverage for the --include-changes switch.

    Without the switch the success summary keeps its exact two-key shape;
    with it the same JSON object gains a "changes" array holding one
    {record, column, before, after} entry per changed cell, in record
    order, and the exported CSV is identical either way.
    """

    # Four data records: the second record's note carries a quoted real
    # newline so record numbers (header is 1) diverge from physical lines.
    CHANGES_ROWS = [
        HEADER,
        [" Alice ", "plain"],          # record 2: trims to "Alice"
        ["Bob", MULTILINE_NOTE],       # record 3: unchanged
        ["   ", QUOTED_NOTE],          # record 4: whitespace-only -> ""
        ["", "x,y"],                   # record 5: already empty, no change
    ]
    CHANGES_EXPECTED_NAMES = ["Alice", "Bob", "", ""]
    CHANGES_EXPECTED = [
        {"record": 2, "column": "name", "before": " Alice ",
         "after": "Alice"},
        {"record": 4, "column": "name", "before": "   ", "after": ""},
    ]

    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.tmpdir = Path(self._tempdir.name)

    def write_input(self, rows, *, bom, tag):
        data = encode_csv(rows, bom=bom)
        path = self.tmpdir / f"input_{tag}.csv"
        path.write_bytes(data)
        return path, data

    def run_cleaner(self, input_path, output_path, *, include_changes,
                    rule="trim", column="name", extra_args=()):
        argv = [
            sys.executable,
            str(SCRIPT_PATH),
            "--input", str(input_path),
            "--output", str(output_path),
            "--column", column,
            "--rule", rule,
        ]
        if include_changes:
            argv.append("--include-changes")
        argv.extend(extra_args)
        return subprocess.run(
            argv, cwd=str(self.tmpdir), capture_output=True
        )

    def read_output_records(self, path):
        # Plain utf-8 (not utf-8-sig) so a stray BOM would surface as content.
        with open(path, "r", encoding="utf-8", newline="") as outfile:
            return list(csv.reader(outfile))

    def test_changes_detail_matches_changed_cells(self):
        for bom in (False, True):
            with self.subTest(bom=bom):
                tag = "changes_bom" if bom else "changes_nobom"
                input_path, original_bytes = self.write_input(
                    self.CHANGES_ROWS, bom=bom, tag=tag
                )
                output_path = self.tmpdir / f"cleaned_{tag}.csv"
                self.assertFalse(output_path.exists())

                result = self.run_cleaner(
                    input_path, output_path, include_changes=True
                )

                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, b"")
                # stdout must consist of exactly one JSON object and
                # nothing else; json.loads rejects trailing non-whitespace.
                summary = json.loads(result.stdout.decode("utf-8"))
                self.assertEqual(
                    summary,
                    {"rows": 4,
                     "changed_cells": 2,
                     "changes": self.CHANGES_EXPECTED},
                )
                # One detail entry per changed cell, nothing more.
                self.assertEqual(
                    len(summary["changes"]), summary["changed_cells"]
                )

                self.assertTrue(output_path.exists())
                raw_output = output_path.read_bytes()
                self.assertFalse(raw_output.startswith(codecs.BOM_UTF8))
                output_rows = self.read_output_records(output_path)
                # Header, record order and the untouched note column
                # (commas, double quotes, embedded newline) are preserved.
                self.assertEqual(output_rows[0], HEADER)
                self.assertEqual(
                    [row[0] for row in output_rows[1:]],
                    self.CHANGES_EXPECTED_NAMES,
                )
                self.assertEqual(
                    [row[1] for row in output_rows],
                    [row[1] for row in self.CHANGES_ROWS],
                )
                # The input file is opened read-only: exact bytes remain.
                self.assertEqual(input_path.read_bytes(), original_bytes)

    def test_export_is_identical_with_and_without_switch(self):
        input_path, _ = self.write_input(
            self.CHANGES_ROWS, bom=False, tag="changes_same_export"
        )
        outputs = {}
        for include_changes in (False, True):
            tag = "with" if include_changes else "without"
            output_path = self.tmpdir / f"cleaned_same_{tag}.csv"
            result = self.run_cleaner(
                input_path, output_path, include_changes=include_changes
            )
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stderr, b"")
            outputs[include_changes] = output_path.read_bytes()
        self.assertEqual(outputs[False], outputs[True])

    def test_summary_without_switch_has_no_changes_key(self):
        input_path, _ = self.write_input(
            self.CHANGES_ROWS, bom=False, tag="changes_off"
        )
        output_path = self.tmpdir / "cleaned_changes_off.csv"

        result = self.run_cleaner(
            input_path, output_path, include_changes=False
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(
            json.loads(result.stdout.decode("utf-8")),
            {"rows": 4, "changed_cells": 2},
        )

    def test_changes_empty_for_header_only_and_unchanged_inputs(self):
        for tag, rows in (
            ("header_only", [HEADER]),
            ("no_changes", [HEADER, ["Alice", "ok"], ["Bob", "x,y"]]),
        ):
            with self.subTest(tag=tag):
                input_path, _ = self.write_input(rows, bom=False, tag=tag)
                output_path = self.tmpdir / f"cleaned_{tag}.csv"

                result = self.run_cleaner(
                    input_path, output_path, include_changes=True
                )

                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, b"")
                summary = json.loads(result.stdout.decode("utf-8"))
                self.assertEqual(summary["changed_cells"], 0)
                self.assertEqual(summary["changes"], [])

    def test_changes_cover_all_rules_and_custom_markers(self):
        # Each rule reports the same {record, column, before, after} shape;
        # duplicate custom markers still yield one entry per changed cell.
        scenarios = [
            ("normalize-null", "name", NULL_ROWS, ["--null-marker", "待补"],
             [
                 {"record": 3, "column": "name", "before": "   ",
                  "after": ""},
                 {"record": 4, "column": "name", "before": "NuLl",
                  "after": ""},
                 {"record": 5, "column": "name", "before": " n/A ",
                  "after": ""},
                 {"record": 11, "column": "name", "before": "　NULL　",
                  "after": ""},
             ]),
            ("normalize-date", "due_date", DATE_ROWS, [],
             [
                 {"record": 2, "column": "due_date",
                  "before": " 29/02/2024 ", "after": "2024-02-29"},
                 {"record": 4, "column": "due_date", "before": "   ",
                  "after": ""},
             ]),
        ]
        for rule, column, rows, extra_args, expected_changes in scenarios:
            with self.subTest(rule=rule):
                input_path, _ = self.write_input(
                    rows, bom=False, tag=f"changes_{rule}"
                )
                output_path = self.tmpdir / f"cleaned_changes_{rule}.csv"

                result = self.run_cleaner(
                    input_path, output_path, include_changes=True,
                    rule=rule, column=column, extra_args=extra_args,
                )

                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, b"")
                summary = json.loads(result.stdout.decode("utf-8"))
                self.assertEqual(summary["changes"], expected_changes)
                self.assertEqual(
                    summary["changed_cells"], len(expected_changes)
                )

    def test_failure_with_switch_prints_no_summary_or_changes(self):
        # The third data record has the wrong field count; with the switch
        # on, the failure shape is unchanged: exit 2, empty stdout, the
        # reason (record 4) on stderr and no output file.
        rows = [
            HEADER,
            [" Alice ", "plain"],
            ["Bob", MULTILINE_NOTE],
            ["   "],
            ["", QUOTED_NOTE],
        ]
        input_path, original_bytes = self.write_input(
            rows, bom=False, tag="changes_bad"
        )
        output_path = self.tmpdir / "cleaned_changes_bad.csv"
        self.assertFalse(output_path.exists())

        result = self.run_cleaner(
            input_path, output_path, include_changes=True
        )

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(
            result.stderr.decode("utf-8"),
            "error: record 4 has 1 field(s), expected 2\n",
        )
        self.assertFalse(output_path.exists())
        self.assertEqual(input_path.read_bytes(), original_bytes)


class DryRunCliTests(unittest.TestCase):
    """Coverage for the --dry-run preview switch.

    A preview goes through the same documented public CLI as a real
    export: the input is fully read and validated and the very same
    summary JSON is printed (with and without --include-changes), but no
    output file, missing parent directory or any other file is created,
    and the input bytes stay untouched. These tests also pin that
    --dry-run skips only the write step: structural validation and both
    output-path protections still fail the run with the documented
    shape. Everything runs through the public CLI with small CSV files
    in private temporary directories; only the standard library is used,
    with no permission settings or fixed absolute paths.
    """

    # name,note header plus four data records. The names are " Alice ",
    # "Bob", three plain spaces and an already-empty string, so only
    # records 2 and 4 (the header is record 1) change under trim. Record
    # 3's note holds a quoted real newline, which must not disturb record
    # numbering; across the note column the rows carry commas, double
    # quotes and that embedded newline, all outside the cleaned column.
    PREVIEW_ROWS = [
        HEADER,
        [" Alice ", 'he said "hi", yes'],   # record 2: trims to "Alice"
        ["Bob", MULTILINE_NOTE],            # record 3: unchanged
        ["   ", QUOTED_NOTE],               # record 4: spaces -> empty
        ["", "plain"],                      # record 5: already empty
    ]
    PREVIEW_EXPECTED_NAMES = ["Alice", "Bob", "", ""]
    PREVIEW_EXPECTED_CHANGES = [
        {"record": 2, "column": "name",
         "before": " Alice ", "after": "Alice"},
        {"record": 4, "column": "name",
         "before": "   ", "after": ""},
    ]

    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.tmpdir = Path(self._tempdir.name)

    def write_input(self, rows, *, tag):
        data = encode_csv(rows, bom=False)
        path = self.tmpdir / f"input_{tag}.csv"
        path.write_bytes(data)
        return path, data

    def run_cleaner(self, input_path, output_path, *, dry_run,
                    include_changes=False, rule="trim", column="name"):
        argv = [
            sys.executable,
            str(SCRIPT_PATH),
            "--input", str(input_path),
            "--output", str(output_path),
            "--column", column,
            "--rule", rule,
        ]
        if include_changes:
            argv.append("--include-changes")
        if dry_run:
            argv.append("--dry-run")
        return subprocess.run(
            argv, cwd=str(self.tmpdir), capture_output=True
        )

    def read_output_records(self, path):
        # Plain utf-8 (not utf-8-sig) so a stray BOM would surface as content.
        with open(path, "r", encoding="utf-8", newline="") as outfile:
            return list(csv.reader(outfile))

    def assert_workspace_holds_only(self, names):
        self.assertEqual(
            sorted(p.name for p in self.tmpdir.iterdir()), sorted(names)
        )

    def test_preview_prints_summary_without_creating_output(self):
        # Without --include-changes the preview stdout is exactly one
        # JSON object with the two documented keys; rows counts data
        # records (4) and changed_cells counts the two trims.
        input_path, original_bytes = self.write_input(
            self.PREVIEW_ROWS, tag="preview"
        )
        output_path = self.tmpdir / "cleaned_preview.csv"
        self.assertFalse(output_path.exists())

        result = self.run_cleaner(
            input_path, output_path, dry_run=True
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        # stdout must consist of exactly one JSON object and nothing
        # else; json.loads rejects trailing non-whitespace.
        self.assertEqual(
            json.loads(result.stdout.decode("utf-8")),
            {"rows": 4, "changed_cells": 2},
        )
        # A successful preview writes nothing: no target file and no
        # other new file, and the input keeps its exact bytes.
        self.assertFalse(output_path.exists())
        self.assertEqual(input_path.read_bytes(), original_bytes)
        self.assert_workspace_holds_only([input_path.name])

    def test_preview_with_changes_lists_records_2_and_4(self):
        # With --include-changes the same object gains a changes array:
        # only the " Alice " record (record 2) and the three-spaces
        # record (record 4) appear, each once, with the original
        # whitespace in before and "Alice" / "" after. The quoted
        # newline in record 3's note does not shift the numbers, and the
        # already-empty record 5 is not listed.
        input_path, original_bytes = self.write_input(
            self.PREVIEW_ROWS, tag="preview_changes"
        )
        output_path = self.tmpdir / "cleaned_preview_changes.csv"
        self.assertFalse(output_path.exists())

        result = self.run_cleaner(
            input_path, output_path, dry_run=True, include_changes=True
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        summary = json.loads(result.stdout.decode("utf-8"))
        self.assertEqual(
            summary,
            {"rows": 4, "changed_cells": 2,
             "changes": self.PREVIEW_EXPECTED_CHANGES},
        )
        # The detail length always equals the changed-cell count.
        self.assertEqual(
            len(summary["changes"]), summary["changed_cells"]
        )
        self.assertFalse(output_path.exists())
        self.assertEqual(input_path.read_bytes(), original_bytes)
        self.assert_workspace_holds_only([input_path.name])

    def test_preview_summary_matches_a_real_export(self):
        # A normal export of the same input prints the identical summary
        # bytes; its target column follows str.strip semantics while the
        # note column (commas, double quotes, embedded newline) is
        # preserved verbatim. The preview path, in contrast, never
        # appears on disk.
        input_path, original_bytes = self.write_input(
            self.PREVIEW_ROWS, tag="preview_vs_export"
        )
        preview_path = self.tmpdir / "cleaned_preview_only.csv"
        export_path = self.tmpdir / "cleaned_export.csv"

        preview = self.run_cleaner(
            input_path, preview_path, dry_run=True
        )
        export = self.run_cleaner(
            input_path, export_path, dry_run=False
        )

        self.assertEqual(preview.returncode, 0)
        self.assertEqual(preview.stderr, b"")
        self.assertEqual(export.returncode, 0)
        self.assertEqual(export.stderr, b"")
        # Same input -> byte-identical summary line on stdout.
        self.assertEqual(preview.stdout, export.stdout)
        self.assertEqual(
            json.loads(export.stdout.decode("utf-8")),
            {"rows": 4, "changed_cells": 2},
        )

        self.assertFalse(preview_path.exists())
        self.assertTrue(export_path.exists())
        self.assertFalse(
            export_path.read_bytes().startswith(codecs.BOM_UTF8)
        )
        output_rows = self.read_output_records(export_path)
        self.assertEqual(output_rows[0], HEADER)
        self.assertEqual(len(output_rows), 5)
        self.assertEqual(
            [row[0] for row in output_rows[1:]],
            self.PREVIEW_EXPECTED_NAMES,
        )
        # The non-target note column keeps every original value.
        self.assertEqual(
            [row[1] for row in output_rows],
            [row[1] for row in self.PREVIEW_ROWS],
        )
        self.assertEqual(input_path.read_bytes(), original_bytes)

    def test_preview_succeeds_when_output_parent_is_missing(self):
        # The output names a free file inside a directory that does not
        # exist; a preview must still succeed (the write is skipped) and
        # must create neither the file nor the missing directory, with
        # or without --include-changes.
        input_path, original_bytes = self.write_input(
            self.PREVIEW_ROWS, tag="preview_missing_dir"
        )
        missing_dir = self.tmpdir / "nodir"
        output_path = missing_dir / "cleaned.csv"
        self.assertFalse(missing_dir.exists())
        self.assertFalse(output_path.exists())

        for include_changes in (False, True):
            with self.subTest(include_changes=include_changes):
                result = self.run_cleaner(
                    input_path, output_path, dry_run=True,
                    include_changes=include_changes,
                )

                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, b"")
                summary = json.loads(result.stdout.decode("utf-8"))
                self.assertEqual(summary["rows"], 4)
                self.assertEqual(summary["changed_cells"], 2)
                if include_changes:
                    self.assertEqual(
                        summary["changes"], self.PREVIEW_EXPECTED_CHANGES
                    )
                else:
                    self.assertNotIn("changes", summary)
                self.assertFalse(output_path.exists())
                self.assertFalse(missing_dir.exists())
                self.assertEqual(input_path.read_bytes(), original_bytes)

        self.assert_workspace_holds_only(
            [input_path.name]
        )

    def test_preview_header_only_file_reports_zero_counts(self):
        # A header-only file previews successfully: both counts are 0,
        # and with --include-changes the changes array is present and
        # empty. No output file is created in either mode.
        input_path, original_bytes = self.write_input(
            [HEADER], tag="preview_header_only"
        )
        output_path = self.tmpdir / "cleaned_preview_header_only.csv"

        for include_changes in (False, True):
            with self.subTest(include_changes=include_changes):
                result = self.run_cleaner(
                    input_path, output_path, dry_run=True,
                    include_changes=include_changes,
                )

                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, b"")
                summary = json.loads(result.stdout.decode("utf-8"))
                expected = {"rows": 0, "changed_cells": 0}
                if include_changes:
                    expected["changes"] = []
                self.assertEqual(summary, expected)
                self.assertFalse(output_path.exists())
                self.assertEqual(input_path.read_bytes(), original_bytes)

    def test_preview_keeps_column_count_failure_boundary(self):
        # A legal record whose note contains a quoted real newline
        # (record 2, two physical lines), one more legal record
        # (record 3), then a record with only one field (record 4).
        # Preview keeps the existing failure shape: exit 2, stdout
        # exactly empty (so neither the already-computed summary nor any
        # changes detail is printed, even with --include-changes), and
        # the record-4 diagnostic naming the actual and expected field
        # counts. Nothing is created and the input bytes stay unchanged.
        rows = [
            HEADER,
            [" Alice ", MULTILINE_NOTE],
            ["Bob", "ok"],
            ["bad"],
        ]
        input_path, original_bytes = self.write_input(
            rows, tag="preview_bad"
        )
        output_path = self.tmpdir / "cleaned_preview_bad.csv"
        self.assertFalse(output_path.exists())

        result = self.run_cleaner(
            input_path, output_path, dry_run=True, include_changes=True
        )

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        stderr_text = result.stderr.decode("utf-8")
        self.assertEqual(
            stderr_text,
            "error: record 4 has 1 field(s), expected 2\n",
        )
        # The required fragments are pinned explicitly as well.
        self.assertIn("record 4", stderr_text)
        self.assertIn("1 field(s)", stderr_text)
        self.assertIn("expected 2", stderr_text)
        self.assertNotIn("Traceback", stderr_text)
        self.assertFalse(output_path.exists())
        self.assertEqual(input_path.read_bytes(), original_bytes)
        self.assert_workspace_holds_only([input_path.name])

    def test_preview_rejects_an_existing_output_file(self):
        # The output path already names a regular file; preview must not
        # treat it as writable just because nothing gets written. The
        # refusal keeps the documented wording, the target survives
        # byte-for-byte and no extra file appears.
        input_path, original_bytes = self.write_input(
            self.PREVIEW_ROWS, tag="preview_exists"
        )
        output_path = self.tmpdir / "cleaned_preview_exists.csv"
        target_bytes = b"pre-existing target bytes\n"
        output_path.write_bytes(target_bytes)

        result = self.run_cleaner(
            input_path, output_path, dry_run=True, include_changes=True
        )

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        stderr_text = result.stderr.decode("utf-8")
        self.assertIn("output file already exists", stderr_text)
        self.assertNotIn("Traceback", stderr_text)
        self.assertEqual(output_path.read_bytes(), target_bytes)
        self.assertEqual(input_path.read_bytes(), original_bytes)
        self.assert_workspace_holds_only(
            [input_path.name, output_path.name]
        )

    def test_preview_rejects_output_path_equal_to_input(self):
        # Output and input naming the same file is rejected in preview
        # mode with the documented wording; the input file is neither
        # deleted nor rewritten and no other file appears.
        input_path, original_bytes = self.write_input(
            self.PREVIEW_ROWS, tag="preview_same"
        )

        result = self.run_cleaner(
            input_path, input_path, dry_run=True, include_changes=True
        )

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        stderr_text = result.stderr.decode("utf-8")
        self.assertIn(
            "output path must be different from the input path",
            stderr_text,
        )
        self.assertNotIn("Traceback", stderr_text)
        self.assertEqual(input_path.read_bytes(), original_bytes)
        self.assert_workspace_holds_only([input_path.name])


class DryRunNormalizeDateTests(unittest.TestCase):
    """Coverage for --dry-run previews of the normalize-date rule.

    The preview must run the full date conversion and validation and
    print the same summary JSON as a real export (with and without
    --include-changes) without creating the output file or any other
    file, and an invalid date must fail the preview with the documented
    record-numbered diagnostic instead of a summary. Everything goes
    through the public CLI with small CSV files in a private temporary
    directory; only the standard library is used.
    """

    # The shared DATE_ROWS sample is exactly the documented preview
    # shape: due_date,note header plus four data records whose dates
    # are " 29/02/2024 ", "2024-03-01", three plain spaces and an
    # already-empty string, so only records 2 and 4 (the header is
    # record 1) change. Record 3's note holds a quoted real newline,
    # which must not disturb record numbering; the other notes carry a
    # comma, double quotes and plain text, all outside the cleaned
    # column.
    PREVIEW_DATE_ROWS = DATE_ROWS
    PREVIEW_DATE_CHANGES = [
        {"record": 2, "column": "due_date",
         "before": " 29/02/2024 ", "after": "2024-02-29"},
        {"record": 4, "column": "due_date",
         "before": "   ", "after": ""},
    ]

    # Same sample with the third date replaced by the impossible
    # 31/02/2024 (record 4) and the fourth by the null-marker text NULL
    # (record 5); the two leading legal records and the quoted-newline
    # note are kept, so the first invalid value sits at record 4.
    INVALID_PREVIEW_ROWS = [
        DATE_HEADER,
        [" 29/02/2024 ", "first, with comma"],
        ["2024-03-01", '他说"好"\n第二行'],
        ["31/02/2024", "plain"],
        ["NULL", "last"],
    ]

    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.tmpdir = Path(self._tempdir.name)

    def write_input(self, rows, *, tag):
        data = encode_csv(rows, bom=False)
        path = self.tmpdir / f"input_{tag}.csv"
        path.write_bytes(data)
        return path, data

    def run_cleaner(self, input_path, output_path, *, dry_run,
                    include_changes=False):
        argv = [
            sys.executable,
            str(SCRIPT_PATH),
            "--input", str(input_path),
            "--output", str(output_path),
            "--column", "due_date",
            "--rule", "normalize-date",
        ]
        if include_changes:
            argv.append("--include-changes")
        if dry_run:
            argv.append("--dry-run")
        return subprocess.run(
            argv, cwd=str(self.tmpdir), capture_output=True
        )

    def read_output_records(self, path):
        # Plain utf-8 (not utf-8-sig) so a stray BOM would surface as content.
        with open(path, "r", encoding="utf-8", newline="") as outfile:
            return list(csv.reader(outfile))

    def assert_workspace_holds_only(self, names):
        self.assertEqual(
            sorted(p.name for p in self.tmpdir.iterdir()), sorted(names)
        )

    def test_date_preview_summary_with_and_without_changes(self):
        # Both preview modes exit 0 with empty stderr and exactly one
        # JSON object on stdout: rows counts the four data records and
        # changed_cells the two normalized cells. Without the switch
        # there is no changes key; with it only records 2 and 4 appear,
        # before keeping the original whitespace exactly and after
        # holding "2024-02-29" / "" -- the quoted newline in record 3's
        # note does not shift the record numbers.
        input_path, original_bytes = self.write_input(
            self.PREVIEW_DATE_ROWS, tag="date_preview"
        )
        output_path = self.tmpdir / "cleaned_date_preview.csv"
        self.assertFalse(output_path.exists())

        for include_changes in (False, True):
            with self.subTest(include_changes=include_changes):
                result = self.run_cleaner(
                    input_path, output_path, dry_run=True,
                    include_changes=include_changes,
                )

                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, b"")
                # stdout must consist of exactly one JSON object and
                # nothing else; json.loads rejects trailing
                # non-whitespace.
                summary = json.loads(result.stdout.decode("utf-8"))
                expected = {"rows": 4, "changed_cells": 2}
                if include_changes:
                    expected["changes"] = self.PREVIEW_DATE_CHANGES
                self.assertEqual(summary, expected)
                if include_changes:
                    # One detail entry per changed cell, nothing more.
                    self.assertEqual(
                        len(summary["changes"]),
                        summary["changed_cells"],
                    )
                else:
                    self.assertNotIn("changes", summary)
                # A successful preview writes nothing: no target file
                # and no other new file, and the input keeps its exact
                # bytes.
                self.assertFalse(output_path.exists())
                self.assertEqual(input_path.read_bytes(), original_bytes)
                self.assert_workspace_holds_only([input_path.name])

    def test_date_preview_summary_matches_real_export(self):
        # Under each --include-changes setting a real export of the same
        # input prints the identical summary as the preview. The export
        # writes 2024-02-29 / 2024-03-01 / "" / "" with the note column
        # (comma, double quotes, embedded newline), the header and the
        # record order preserved, while the preview path never appears
        # on disk.
        input_path, original_bytes = self.write_input(
            self.PREVIEW_DATE_ROWS, tag="date_preview_vs_export"
        )

        for include_changes in (False, True):
            with self.subTest(include_changes=include_changes):
                tag = "with" if include_changes else "without"
                preview_path = self.tmpdir / f"cleaned_preview_{tag}.csv"
                export_path = self.tmpdir / f"cleaned_export_{tag}.csv"

                preview = self.run_cleaner(
                    input_path, preview_path, dry_run=True,
                    include_changes=include_changes,
                )
                export = self.run_cleaner(
                    input_path, export_path, dry_run=False,
                    include_changes=include_changes,
                )

                self.assertEqual(preview.returncode, 0)
                self.assertEqual(preview.stderr, b"")
                self.assertEqual(export.returncode, 0)
                self.assertEqual(export.stderr, b"")
                # Same input and switches -> byte-identical summary.
                self.assertEqual(preview.stdout, export.stdout)
                summary = json.loads(export.stdout.decode("utf-8"))
                self.assertEqual(summary["rows"], 4)
                self.assertEqual(summary["changed_cells"], 2)

                self.assertFalse(preview_path.exists())
                self.assertTrue(export_path.exists())
                self.assertFalse(
                    export_path.read_bytes().startswith(codecs.BOM_UTF8)
                )
                output_rows = self.read_output_records(export_path)
                # Header and record order are unchanged.
                self.assertEqual(output_rows[0], DATE_HEADER)
                self.assertEqual(len(output_rows), 5)
                # The due_date column is normalized per row.
                self.assertEqual(
                    [row[0] for row in output_rows[1:]],
                    DATE_EXPECTED_DATES,
                )
                # The note column is never cleaned: commas, double
                # quotes and the embedded newline round-trip exactly.
                self.assertEqual(
                    [row[1] for row in output_rows],
                    [row[1] for row in self.PREVIEW_DATE_ROWS],
                )
                self.assertEqual(input_path.read_bytes(), original_bytes)

        # Only the two export files were added next to the input.
        self.assert_workspace_holds_only(
            [input_path.name,
             "cleaned_export_with.csv", "cleaned_export_without.csv"]
        )

    def test_date_preview_first_invalid_date_fails_by_record_number(self):
        # Record 3's note contains a quoted real newline, so it spans
        # two physical lines but counts as one CSV record. The first
        # invalid date is 31/02/2024 at record 4; the NULL text at
        # record 5 must never be reported because the run aborts at the
        # first failure. With and without --include-changes the preview
        # exits 2 with stdout exactly empty (so neither the
        # already-computed summary nor any changes detail is printed),
        # the diagnostic on stderr and no output file or other new file.
        input_path, original_bytes = self.write_input(
            self.INVALID_PREVIEW_ROWS, tag="date_preview_invalid"
        )
        output_path = self.tmpdir / "cleaned_date_preview_invalid.csv"
        self.assertFalse(output_path.exists())

        for include_changes in (False, True):
            with self.subTest(include_changes=include_changes):
                result = self.run_cleaner(
                    input_path, output_path, dry_run=True,
                    include_changes=include_changes,
                )

                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, b"")
                stderr_text = result.stderr.decode("utf-8")
                self.assertIn("invalid date", stderr_text)
                self.assertIn("due_date", stderr_text)
                self.assertIn("record 4", stderr_text)
                # The message quotes the first offending value verbatim.
                self.assertIn("31/02/2024", stderr_text)
                # Only the first invalid date is reported; the later
                # NULL record must not appear in the message.
                self.assertNotIn("record 5", stderr_text)
                self.assertNotIn("NULL", stderr_text)
                self.assertNotIn("Traceback", stderr_text)
                self.assertFalse(output_path.exists())
                self.assertEqual(input_path.read_bytes(), original_bytes)
                self.assert_workspace_holds_only([input_path.name])

    def test_date_preview_accepts_ymd_slash_spelling(self):
        # --dry-run must accept the YYYY/MM/DD spelling and give the same
        # summary as a real export without creating the output file. The
        # sample mixes all three spellings; only records 2, 3 and 5
        # change (the header is record 1).
        input_path, original_bytes = self.write_input(
            MIXED_DATE_ROWS, tag="date_preview_mixed"
        )
        output_path = self.tmpdir / "cleaned_date_preview_mixed.csv"
        self.assertFalse(output_path.exists())

        for include_changes in (False, True):
            with self.subTest(include_changes=include_changes):
                result = self.run_cleaner(
                    input_path, output_path, dry_run=True,
                    include_changes=include_changes,
                )

                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, b"")
                summary = json.loads(result.stdout.decode("utf-8"))
                expected = {
                    "rows": 4,
                    "changed_cells": MIXED_DATE_EXPECTED_CHANGED,
                }
                if include_changes:
                    expected["changes"] = MIXED_DATE_EXPECTED_CHANGES_DETAIL
                self.assertEqual(summary, expected)
                self.assertFalse(output_path.exists())
                self.assertEqual(input_path.read_bytes(), original_bytes)
                self.assert_workspace_holds_only([input_path.name])

    def test_date_preview_rejects_ymd_slash_invalid_spellings(self):
        # Invalid YYYY/MM/DD values fail the preview exactly like the
        # other two spellings: exit 2, empty stdout, the first offending
        # value quoted at record 2, no output file or other new file.
        for value in ("2024/2/29", "2024/02/30", "0000/01/01",
                      "２０２４/０２/２９", "2024/02/29 10:30",
                      "2024 /02/29"):
            with self.subTest(value=value):
                input_path, _ = self.write_input(
                    [DATE_HEADER, [value, "note"]],
                    tag="date_preview_ymd_bad",
                )
                output_path = self.tmpdir / "cleaned_preview_ymd_bad.csv"

                result = self.run_cleaner(
                    input_path, output_path, dry_run=True,
                )

                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, b"")
                stderr_text = result.stderr.decode("utf-8")
                self.assertIn("invalid date", stderr_text)
                self.assertIn("due_date", stderr_text)
                self.assertIn("record 2", stderr_text)
                self.assertIn(value, stderr_text)
                self.assertFalse(output_path.exists())

    def test_date_preview_accepts_dot_spelling(self):
        # --dry-run must accept the YYYY.MM.DD spelling, mixed with an
        # ISO date and an empty cell, and give the same summary as a
        # real export (records 2 and 3 only) without creating the
        # output file or any other new file.
        input_path, original_bytes = self.write_input(
            DOT_DATE_ROWS, tag="date_preview_dot"
        )
        output_path = self.tmpdir / "cleaned_date_preview_dot.csv"
        self.assertFalse(output_path.exists())

        for include_changes in (False, True):
            with self.subTest(include_changes=include_changes):
                result = self.run_cleaner(
                    input_path, output_path, dry_run=True,
                    include_changes=include_changes,
                )

                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, b"")
                summary = json.loads(result.stdout.decode("utf-8"))
                expected = {
                    "rows": 4,
                    "changed_cells": DOT_DATE_EXPECTED_CHANGED,
                }
                if include_changes:
                    expected["changes"] = DOT_DATE_EXPECTED_CHANGES_DETAIL
                self.assertEqual(summary, expected)
                self.assertFalse(output_path.exists())
                self.assertEqual(input_path.read_bytes(), original_bytes)
                self.assert_workspace_holds_only([input_path.name])

    def test_date_preview_dot_summary_matches_real_export(self):
        # A preview and a real export of the dot sample print the
        # identical summary; the export converts the due_date column to
        # 2024-02-29 / 0001-01-01 / 2024-03-01 / "" while preserving
        # the header, record order and notes, and the preview path
        # never appears on disk.
        input_path, original_bytes = self.write_input(
            DOT_DATE_ROWS, tag="date_preview_dot_vs_export"
        )
        preview_path = self.tmpdir / "cleaned_preview_dot.csv"
        export_path = self.tmpdir / "cleaned_export_dot.csv"

        preview = self.run_cleaner(
            input_path, preview_path, dry_run=True, include_changes=True
        )
        export = self.run_cleaner(
            input_path, export_path, dry_run=False, include_changes=True
        )

        self.assertEqual(preview.returncode, 0)
        self.assertEqual(preview.stderr, b"")
        self.assertEqual(export.returncode, 0)
        self.assertEqual(export.stderr, b"")
        self.assertEqual(preview.stdout, export.stdout)
        summary = json.loads(export.stdout.decode("utf-8"))
        self.assertEqual(summary["rows"], 4)
        self.assertEqual(
            summary["changed_cells"], DOT_DATE_EXPECTED_CHANGED
        )
        self.assertEqual(
            summary["changes"], DOT_DATE_EXPECTED_CHANGES_DETAIL
        )
        self.assertFalse(preview_path.exists())
        self.assertTrue(export_path.exists())
        self.assertFalse(
            export_path.read_bytes().startswith(codecs.BOM_UTF8)
        )
        output_rows = self.read_output_records(export_path)
        self.assertEqual(output_rows[0], DATE_HEADER)
        self.assertEqual(
            [row[0] for row in output_rows[1:]], DOT_DATE_EXPECTED_DATES
        )
        self.assertEqual(
            [row[1] for row in output_rows],
            [row[1] for row in DOT_DATE_ROWS],
        )
        self.assertEqual(input_path.read_bytes(), original_bytes)

    def test_date_preview_rejects_dot_non_leap_by_record_number(self):
        # The 2023.02.29 at record 3 fails the preview with exit 2,
        # empty stdout, the column, record number and original value on
        # stderr, no traceback, and no output file or other new file.
        input_path, original_bytes = self.write_input(
            DOT_INVALID_ROWS, tag="date_preview_dot_invalid"
        )
        output_path = self.tmpdir / "cleaned_date_preview_dot_invalid.csv"
        self.assertFalse(output_path.exists())

        for include_changes in (False, True):
            with self.subTest(include_changes=include_changes):
                result = self.run_cleaner(
                    input_path, output_path, dry_run=True,
                    include_changes=include_changes,
                )

                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, b"")
                stderr_text = result.stderr.decode("utf-8")
                self.assertIn("invalid date", stderr_text)
                self.assertIn("due_date", stderr_text)
                self.assertIn("record 3", stderr_text)
                self.assertIn("2023.02.29", stderr_text)
                self.assertNotIn("record 4", stderr_text)
                self.assertNotIn("record 5", stderr_text)
                self.assertNotIn("Traceback", stderr_text)
                self.assertFalse(output_path.exists())
                self.assertEqual(input_path.read_bytes(), original_bytes)
                self.assert_workspace_holds_only([input_path.name])

    def test_date_preview_rejects_dot_invalid_spellings(self):
        # Invalid YYYY.MM.DD values fail the preview exactly like the
        # other spellings: exit 2, empty stdout, the first offending
        # value quoted at record 2, no output file or other new file.
        for value in ("2024.2.29", "2024.02.1", "2023.02.29",
                      "0000.01.01", "２０２４.０２.２９",
                      "2024.02.29 10:30", "2024 .02.29",
                      "01.02.2024", "2024-02.29", "2024/02.29",
                      "2024。02。29"):
            with self.subTest(value=value):
                input_path, _ = self.write_input(
                    [DATE_HEADER, [value, "note"]],
                    tag="date_preview_dot_bad",
                )
                output_path = self.tmpdir / "cleaned_preview_dot_bad.csv"

                result = self.run_cleaner(
                    input_path, output_path, dry_run=True,
                )

                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, b"")
                stderr_text = result.stderr.decode("utf-8")
                self.assertIn("invalid date", stderr_text)
                self.assertIn("due_date", stderr_text)
                self.assertIn("record 2", stderr_text)
                self.assertIn(value, stderr_text)
                self.assertFalse(output_path.exists())


class DryRunNullMarkerTests(unittest.TestCase):
    """Coverage for --dry-run previews of normalize-null with markers.

    The repeatable --null-marker option and the --dry-run preview are
    both documented public features; these tests pin their combination
    end to end through the public CLI. The main sample is a BOM-prefixed
    UTF-8 CSV whose name column exercises a custom marker with
    surrounding whitespace, a default marker, a whitespace-only cell, an
    already-empty cell, two near-miss values that must keep their
    surrounding whitespace, and a mixed-case default NULL. The preview
    prints the same summary JSON as a real export (with and without
    --include-changes) while creating neither the output file nor its
    missing parent directory, and a whitespace-only marker is rejected
    even on a header-only input. Everything runs in a private temporary
    directory using only the standard library.
    """

    # Four custom markers. "MISSING" and "missing" strip/lower to the
    # same key, so they collapse into one effective marker and can never
    # inflate the change count; " n/A " strips to the default N/A
    # marker; "ä" only matches that exact lowercase spelling because
    # case folding is ASCII-only (so " Ä " in the data is not a match).
    PREVIEW_MARKERS = ["MISSING", "missing", " n/A ", "ä"]

    # name,note header plus seven data records. The second record's
    # note holds a quoted real newline, which must not disturb record
    # numbering (the header is record 1); the other notes carry a
    # comma, double quotes and plain text, all outside the cleaned
    # column.
    PREVIEW_NULL_ROWS = [
        HEADER,
        [" MISSING ", "plain text"],          # record 2: custom marker
        [" n/A ", MULTILINE_NOTE],            # record 3: default marker
        ["   ", "comma, inside"],             # record 4: whitespace-only
        ["", QUOTED_NOTE],                    # record 5: already empty
        [" NULLABLE ", "tail, with comma"],   # record 6: kept verbatim
        [" Ä ", "plain"],                     # record 7: non-ASCII case
        ["NuLl", 'she said "bye"'],           # record 8: default NULL
    ]
    # Records 2, 3, 4 and 8 become empty strings; record 5 was already
    # empty (not counted as a change) and records 6 and 7 survive
    # character-for-character including their surrounding spaces.
    PREVIEW_EXPECTED_NAMES = [
        "", "", "", "", " NULLABLE ", " Ä ", "",
    ]
    PREVIEW_EXPECTED_CHANGES = [
        {"record": 2, "column": "name",
         "before": " MISSING ", "after": ""},
        {"record": 3, "column": "name",
         "before": " n/A ", "after": ""},
        {"record": 4, "column": "name",
         "before": "   ", "after": ""},
        {"record": 8, "column": "name",
         "before": "NuLl", "after": ""},
    ]

    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.tmpdir = Path(self._tempdir.name)

    def write_input(self, rows, *, tag, bom=True):
        data = encode_csv(rows, bom=bom)
        path = self.tmpdir / f"input_{tag}.csv"
        path.write_bytes(data)
        return path, data

    def run_cleaner(self, input_path, output_path, *, dry_run,
                    include_changes=False, markers=PREVIEW_MARKERS):
        argv = [
            sys.executable,
            str(SCRIPT_PATH),
            "--input", str(input_path),
            "--output", str(output_path),
            "--column", "name",
            "--rule", "normalize-null",
        ]
        for marker in markers:
            argv.extend(["--null-marker", marker])
        if include_changes:
            argv.append("--include-changes")
        if dry_run:
            argv.append("--dry-run")
        return subprocess.run(
            argv, cwd=str(self.tmpdir), capture_output=True
        )

    def read_output_records(self, path):
        # Plain utf-8 (not utf-8-sig) so a stray BOM would surface as content.
        with open(path, "r", encoding="utf-8", newline="") as outfile:
            return list(csv.reader(outfile))

    def assert_workspace_holds_only(self, names):
        self.assertEqual(
            sorted(p.name for p in self.tmpdir.iterdir()), sorted(names)
        )

    def test_preview_summary_with_and_without_changes(self):
        # The output path names a free file inside a directory that does
        # not exist; the preview must still succeed and must create
        # neither the file nor the missing directory. Without
        # --include-changes the summary keeps its exact two-key shape;
        # with it only records 2, 3, 4 and 8 are listed, in record
        # order, each with the original value in before and "" after.
        input_path, original_bytes = self.write_input(
            self.PREVIEW_NULL_ROWS, tag="marker_preview"
        )
        # Pin the scenario precondition: the input really carries a BOM.
        self.assertTrue(original_bytes.startswith(codecs.BOM_UTF8))
        missing_dir = self.tmpdir / "nodir"
        output_path = missing_dir / "cleaned.csv"
        self.assertFalse(missing_dir.exists())
        self.assertFalse(output_path.exists())

        for include_changes in (False, True):
            with self.subTest(include_changes=include_changes):
                result = self.run_cleaner(
                    input_path, output_path, dry_run=True,
                    include_changes=include_changes,
                )

                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, b"")
                # stdout must consist of exactly one JSON object and
                # nothing else; json.loads rejects trailing
                # non-whitespace. Comparison is by parsed content, so
                # key order is irrelevant.
                summary = json.loads(result.stdout.decode("utf-8"))
                expected = {"rows": 7, "changed_cells": 4}
                if include_changes:
                    expected["changes"] = self.PREVIEW_EXPECTED_CHANGES
                self.assertEqual(summary, expected)
                if include_changes:
                    # One detail entry per changed cell, nothing more.
                    self.assertEqual(
                        len(summary["changes"]),
                        summary["changed_cells"],
                    )
                else:
                    self.assertNotIn("changes", summary)
                # A successful preview writes nothing: no target file,
                # no missing parent directory, and the input keeps its
                # exact bytes.
                self.assertFalse(output_path.exists())
                self.assertFalse(missing_dir.exists())
                self.assertEqual(input_path.read_bytes(), original_bytes)

        self.assert_workspace_holds_only([input_path.name])

    def test_export_summary_matches_preview(self):
        # Under each --include-changes setting a real export of the same
        # input prints the identical summary as the preview (compared by
        # parsed content, not key order). The export is BOM-free, holds
        # the expected name column, and preserves the header, the record
        # order and every note value, while the preview path and its
        # missing parent directory never appear on disk.
        input_path, original_bytes = self.write_input(
            self.PREVIEW_NULL_ROWS, tag="marker_preview_vs_export"
        )
        missing_dir = self.tmpdir / "nodir"

        for include_changes in (False, True):
            with self.subTest(include_changes=include_changes):
                tag = "with" if include_changes else "without"
                preview_path = missing_dir / f"preview_{tag}.csv"
                export_path = self.tmpdir / f"cleaned_export_{tag}.csv"

                preview = self.run_cleaner(
                    input_path, preview_path, dry_run=True,
                    include_changes=include_changes,
                )
                export = self.run_cleaner(
                    input_path, export_path, dry_run=False,
                    include_changes=include_changes,
                )

                self.assertEqual(preview.returncode, 0)
                self.assertEqual(preview.stderr, b"")
                self.assertEqual(export.returncode, 0)
                self.assertEqual(export.stderr, b"")
                # Same input and switches -> same summary content.
                preview_summary = json.loads(preview.stdout.decode("utf-8"))
                export_summary = json.loads(export.stdout.decode("utf-8"))
                self.assertEqual(preview_summary, export_summary)
                expected = {"rows": 7, "changed_cells": 4}
                if include_changes:
                    expected["changes"] = self.PREVIEW_EXPECTED_CHANGES
                self.assertEqual(export_summary, expected)

                self.assertFalse(preview_path.exists())
                self.assertFalse(missing_dir.exists())
                self.assertTrue(export_path.exists())
                self.assertFalse(
                    export_path.read_bytes().startswith(codecs.BOM_UTF8)
                )
                output_rows = self.read_output_records(export_path)
                # Header and record order are unchanged.
                self.assertEqual(output_rows[0], HEADER)
                self.assertEqual(len(output_rows), 8)
                # The name column follows the per-row expectations.
                self.assertEqual(
                    [row[0] for row in output_rows[1:]],
                    self.PREVIEW_EXPECTED_NAMES,
                )
                # The note column is never cleaned: the comma, double
                # quotes, embedded newline and plain text round-trip
                # exactly.
                self.assertEqual(
                    [row[1] for row in output_rows],
                    [row[1] for row in self.PREVIEW_NULL_ROWS],
                )
                self.assertEqual(input_path.read_bytes(), original_bytes)

        # Only the two export files were added next to the input.
        self.assert_workspace_holds_only(
            [input_path.name,
             "cleaned_export_with.csv", "cleaned_export_without.csv"]
        )

    def test_preview_header_only_reports_zero_counts(self):
        # A header-only input with valid markers previews successfully:
        # both counts are 0, and with --include-changes the changes
        # array is present and empty. No output file is created.
        input_path, original_bytes = self.write_input(
            [HEADER], tag="marker_preview_header_only"
        )
        output_path = self.tmpdir / "cleaned_marker_header_only.csv"
        self.assertFalse(output_path.exists())

        for include_changes in (False, True):
            with self.subTest(include_changes=include_changes):
                result = self.run_cleaner(
                    input_path, output_path, dry_run=True,
                    include_changes=include_changes,
                )

                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, b"")
                summary = json.loads(result.stdout.decode("utf-8"))
                expected = {"rows": 0, "changed_cells": 0}
                if include_changes:
                    expected["changes"] = []
                self.assertEqual(summary, expected)
                self.assertFalse(output_path.exists())
                self.assertEqual(input_path.read_bytes(), original_bytes)

        self.assert_workspace_holds_only([input_path.name])

    def test_whitespace_only_marker_rejected_even_on_header_only(self):
        # A marker that is empty after str.strip() is a parameter error,
        # so it fails even when the header-only input would leave the
        # marker nothing to match: exit 2, stdout exactly empty (no
        # summary, no changes detail), the --null-marker / non-empty
        # reason on stderr, no Python traceback and no new files.
        input_path, original_bytes = self.write_input(
            [HEADER], tag="marker_preview_blank"
        )
        output_path = self.tmpdir / "cleaned_marker_blank.csv"
        self.assertFalse(output_path.exists())

        for include_changes in (False, True):
            with self.subTest(include_changes=include_changes):
                result = self.run_cleaner(
                    input_path, output_path, dry_run=True,
                    include_changes=include_changes,
                    markers=["   "],
                )

                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, b"")
                stderr_text = result.stderr.decode("utf-8")
                self.assertIn("--null-marker", stderr_text)
                self.assertIn("non-empty", stderr_text)
                self.assertNotIn("Traceback", stderr_text)
                self.assertFalse(output_path.exists())
                self.assertEqual(input_path.read_bytes(), original_bytes)

        self.assert_workspace_holds_only([input_path.name])


class ArgumentValidationTests(unittest.TestCase):
    """Required-option and unsupported-rule rejection via the public CLI.

    A single legal UTF-8 sample -- header name,note plus one record
    whose name parses as " Alice " and whose note parses as "x,y" --
    isolates the argument errors from any data problem: every failure
    below runs against input the tool would otherwise clean happily.
    """

    # The note carries a comma so it must stay quoted; the name carries
    # surrounding spaces so trim has exactly one cell to change.
    INPUT_BYTES = b'name,note\n" Alice ","x,y"\n'

    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.tmpdir = Path(self._tempdir.name)
        self.input_path = self.tmpdir / "input.csv"
        self.input_path.write_bytes(self.INPUT_BYTES)
        # The designated output is a fresh name next to the input.
        self.output_path = self.tmpdir / "cleaned.csv"

    def valid_args(self):
        """The four required options, all valid for the sample input."""
        return [
            "--input", str(self.input_path),
            "--output", str(self.output_path),
            "--column", "name",
            "--rule", "trim",
        ]

    def run_cleaner(self, args):
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH), *args],
            cwd=str(self.tmpdir), capture_output=True,
        )

    def assert_no_side_effects(self):
        """Input bytes intact, no output file, no new files at all.

        With --output omitted this also proves no implicit output is
        generated anywhere in the directory.
        """
        self.assertEqual(self.input_path.read_bytes(), self.INPUT_BYTES)
        self.assertFalse(self.output_path.exists())
        self.assertEqual(
            [p.name for p in self.tmpdir.iterdir()], ["input.csv"]
        )

    def test_missing_required_option_is_rejected(self):
        # Dropping any one of the four required options from an
        # otherwise valid call must exit 2 with a byte-for-byte empty
        # stdout and the omitted option name on stderr, without a
        # Python traceback; the usage text itself, its punctuation and
        # the argument order are deliberately not pinned.
        for option in ("--input", "--output", "--column", "--rule"):
            with self.subTest(missing=option):
                args = self.valid_args()
                index = args.index(option)
                del args[index:index + 2]

                result = self.run_cleaner(args)

                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, b"")
                stderr_text = result.stderr.decode(
                    "utf-8", errors="replace"
                )
                self.assertIn(option, stderr_text)
                self.assertNotIn("Traceback", stderr_text)
                self.assert_no_side_effects()

    def test_unsupported_rule_is_rejected(self):
        # "unknown-rule" is simply not a rule; "Trim" differs from the
        # supported "trim" only by letter case, and rule names are
        # case-sensitive. Both must exit 2 with an empty stdout -- with
        # and without --include-changes, so neither the summary nor a
        # changes array is printed -- and a stderr reason naming the
        # unsupported rule and echoing the passed value.
        for rule in ("unknown-rule", "Trim"):
            for include_changes in (False, True):
                with self.subTest(
                    rule=rule, include_changes=include_changes
                ):
                    args = self.valid_args()
                    args[args.index("--rule") + 1] = rule
                    if include_changes:
                        args.append("--include-changes")

                    result = self.run_cleaner(args)

                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stdout, b"")
                    stderr_text = result.stderr.decode(
                        "utf-8", errors="replace"
                    )
                    self.assertIn("unsupported rule", stderr_text)
                    self.assertIn(rule, stderr_text)
                    self.assertNotIn("Traceback", stderr_text)
                    self.assert_no_side_effects()

    def test_valid_trim_call_with_changes_is_the_success_control(self):
        # The same input with every argument valid proves the failures
        # above are caused by the argument errors, not by the sample:
        # exit 0, empty stderr, and the summary with the changes detail
        # for the single trimmed cell at record 2 (header is record 1).
        result = self.run_cleaner(self.valid_args() + ["--include-changes"])

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(
            json.loads(result.stdout.decode("utf-8")),
            {
                "rows": 1,
                "changed_cells": 1,
                "changes": [
                    {
                        "record": 2,
                        "column": "name",
                        "before": " Alice ",
                        "after": "Alice",
                    }
                ],
            },
        )
        output_bytes = self.output_path.read_bytes()
        self.assertFalse(output_bytes.startswith(codecs.BOM_UTF8))
        # Plain utf-8 (not utf-8-sig) so a stray BOM would surface.
        with open(
            self.output_path, "r", encoding="utf-8", newline=""
        ) as outfile:
            self.assertEqual(
                list(csv.reader(outfile)),
                [HEADER, ["Alice", "x,y"]],
            )
        self.assertEqual(self.input_path.read_bytes(), self.INPUT_BYTES)


class DateOrderCliTests(unittest.TestCase):
    """Coverage for the optional normalize-date --date-order switch.

    Every test goes through the documented public CLI against small CSV
    files in a private temporary directory: no external files or network.
    Results are judged on parsed CSV fields and the parsed JSON object,
    so equivalent quoting styles and JSON key order are irrelevant.
    """

    # The acceptance sample: 05/06/2024 is ambiguous on purpose, the
    # other rows pin that YYYY/MM/DD and YYYY-MM-DD stay year-month-day
    # under either order and that an empty cell stays empty.
    ORDER_ROWS = [
        DATE_HEADER,
        ["05/06/2024", "alpha"],       # 2024-05-06 (mdy) / 2024-06-05 (dmy)
        ["2024/02/29", "beta"],        # YYYY/MM/DD -> 2024-02-29 either way
        ["2024-01-01", "gamma"],       # already ISO: not a change
        ["", "delta"],                 # already empty: not a change
    ]
    ORDER_EXPECTED_MDY = ["2024-05-06", "2024-02-29", "2024-01-01", ""]
    ORDER_EXPECTED_DMY = ["2024-06-05", "2024-02-29", "2024-01-01", ""]
    ORDER_EXPECTED_CHANGED = 2
    ORDER_CHANGES_MDY = [
        {"record": 2, "column": "due_date",
         "before": "05/06/2024", "after": "2024-05-06"},
        {"record": 3, "column": "due_date",
         "before": "2024/02/29", "after": "2024-02-29"},
    ]

    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.tmpdir = Path(self._tempdir.name)

    def write_input(self, rows, *, tag):
        path = self.tmpdir / f"input_{tag}.csv"
        path.write_bytes(encode_csv(rows, bom=False))
        return path

    def run_cleaner(self, input_path, output_path, *, order="OMITTED",
                    rule="normalize-date", column="due_date",
                    include_changes=False):
        # order="OMITTED" means the option is not passed at all; None
        # means the bare flag with no following value.
        argv = [
            sys.executable, str(SCRIPT_PATH),
            "--input", str(input_path),
            "--output", str(output_path),
            "--column", column,
            "--rule", rule,
        ]
        if order != "OMITTED":
            argv.append("--date-order")
            if order is not None:
                argv.append(order)
        if include_changes:
            argv.append("--include-changes")
        return subprocess.run(
            argv, cwd=str(self.tmpdir), capture_output=True
        )

    def read_output_records(self, path):
        with open(path, "r", encoding="utf-8", newline="") as outfile:
            return list(csv.reader(outfile))

    def test_mdy_reads_year_last_slash_dates_as_month_day(self):
        input_path = self.write_input(self.ORDER_ROWS, tag="order_mdy")
        output_path = self.tmpdir / "cleaned_order_mdy.csv"

        result = self.run_cleaner(input_path, output_path, order="mdy")

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(
            json.loads(result.stdout.decode("utf-8")),
            {"rows": 4, "changed_cells": self.ORDER_EXPECTED_CHANGED},
        )
        output_rows = self.read_output_records(output_path)
        self.assertEqual(output_rows[0], DATE_HEADER)
        self.assertEqual(
            [row[0] for row in output_rows[1:]], self.ORDER_EXPECTED_MDY
        )
        # The note column, header and record order round-trip untouched.
        self.assertEqual(
            [row[1] for row in output_rows],
            [row[1] for row in self.ORDER_ROWS],
        )
        self.assertFalse(
            output_path.read_bytes().startswith(codecs.BOM_UTF8)
        )

    def test_dmy_explicit_and_omitted_keep_day_month_reading(self):
        # Omitting the option is exactly dmy: both runs export the same
        # dates, starting with 2024-06-05 for the ambiguous value.
        for tag, order in (("dmy_explicit", "dmy"), ("dmy_omitted", "OMITTED")):
            with self.subTest(order=order):
                input_path = self.write_input(self.ORDER_ROWS, tag=tag)
                output_path = self.tmpdir / f"cleaned_{tag}.csv"

                result = self.run_cleaner(input_path, output_path, order=order)

                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, b"")
                self.assertEqual(
                    json.loads(result.stdout.decode("utf-8")),
                    {"rows": 4,
                     "changed_cells": self.ORDER_EXPECTED_CHANGED},
                )
                self.assertEqual(
                    [row[0] for row in self.read_output_records(output_path)[1:]],
                    self.ORDER_EXPECTED_DMY,
                )

    def test_mdy_changes_detail_uses_ordered_after_value(self):
        input_path = self.write_input(self.ORDER_ROWS, tag="order_changes")
        output_path = self.tmpdir / "cleaned_order_changes.csv"

        result = self.run_cleaner(
            input_path, output_path, order="mdy", include_changes=True
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        summary = json.loads(result.stdout.decode("utf-8"))
        self.assertEqual(summary["rows"], 4)
        self.assertEqual(
            summary["changed_cells"], self.ORDER_EXPECTED_CHANGED
        )
        self.assertEqual(summary["changes"], self.ORDER_CHANGES_MDY)
        # No new summary fields beyond the documented three under the
        # switch.
        self.assertEqual(
            sorted(summary), ["changed_cells", "changes", "rows"]
        )

    def test_dot_dates_stay_year_month_day_under_either_order(self):
        # YYYY.MM.DD is independent of --date-order: under mdy, dmy and
        # with the option omitted it converts identically, including the
        # leap day and the 0001 endpoint. A dot value with the year last
        # is not an accepted spelling under either order.
        rows = [
            DATE_HEADER,
            ["2024.02.29", "leap"],
            ["2024.03.05", "ambiguous-looking"],
            ["0001.01.01", "low endpoint"],
        ]
        for tag, order in (("dot_mdy", "mdy"), ("dot_dmy", "dmy"),
                           ("dot_omitted", "OMITTED")):
            with self.subTest(order=order):
                input_path = self.write_input(rows, tag=tag)
                output_path = self.tmpdir / f"cleaned_{tag}.csv"

                result = self.run_cleaner(
                    input_path, output_path, order=order
                )

                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, b"")
                self.assertEqual(
                    json.loads(result.stdout.decode("utf-8")),
                    {"rows": 3, "changed_cells": 3},
                )
                self.assertEqual(
                    [row[0]
                     for row in self.read_output_records(output_path)[1:]],
                    ["2024-02-29", "2024-03-05", "0001-01-01"],
                )

    def test_year_last_dot_value_rejected_under_both_orders(self):
        # Dots never give a year-last spelling: 03.02.2024 cannot be
        # read as a slash date under either order and fails at record 2.
        for order in ("dmy", "mdy"):
            with self.subTest(order=order):
                input_path = self.write_input(
                    [DATE_HEADER, ["03.02.2024", "note"]],
                    tag=f"dot_year_last_{order}",
                )
                output_path = self.tmpdir / (
                    f"cleaned_dot_year_last_{order}.csv"
                )

                result = self.run_cleaner(
                    input_path, output_path, order=order
                )

                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, b"")
                stderr_text = result.stderr.decode("utf-8")
                self.assertIn("invalid date", stderr_text)
                self.assertIn("due_date", stderr_text)
                self.assertIn("record 2", stderr_text)
                self.assertIn("03.02.2024", stderr_text)
                self.assertNotIn("Traceback", stderr_text)
                self.assertFalse(output_path.exists())

    def test_mdy_rejects_impossible_dates_by_record_number(self):
        # Record 2's note contains a quoted real newline, so it spans two
        # physical lines but counts as one CSV record. Each impossible
        # mdy date sits at record 3 and a second invalid date at record 4
        # must never be reported: the first failure aborts the run.
        for value in ("13/02/2024", "02/30/2024"):
            with self.subTest(value=value):
                rows = [
                    DATE_HEADER,
                    ["05/06/2024", MULTILINE_NOTE],
                    [value, "candidate"],
                    ["12/31/9999", "valid mdy, never reached"],
                ]
                input_path = self.write_input(rows, tag="order_bad")
                output_path = self.tmpdir / "cleaned_order_bad.csv"
                self.assertFalse(output_path.exists())

                result = self.run_cleaner(
                    input_path, output_path, order="mdy"
                )

                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, b"")
                stderr_text = result.stderr.decode("utf-8")
                self.assertIn("invalid date", stderr_text)
                self.assertIn("due_date", stderr_text)
                self.assertIn("record 3", stderr_text)
                self.assertIn(value, stderr_text)
                self.assertNotIn("record 4", stderr_text)
                self.assertNotIn("Traceback", stderr_text)
                self.assertFalse(output_path.exists())

    def test_ambiguous_value_follows_chosen_order_without_fallback(self):
        # 13/02/2024 is impossible as month 13 under mdy but a perfectly
        # valid day-13 February date under dmy: the chosen order decides,
        # there is no swapping or guessing when mdy parsing fails.
        rows = [DATE_HEADER, ["13/02/2024", "ambiguous"]]
        input_path = self.write_input(rows, tag="order_ambiguity")

        mdy_output = self.tmpdir / "cleaned_ambiguity_mdy.csv"
        mdy_result = self.run_cleaner(input_path, mdy_output, order="mdy")
        self.assertEqual(mdy_result.returncode, 2)
        self.assertEqual(mdy_result.stdout, b"")
        self.assertIn("record 2", mdy_result.stderr.decode("utf-8"))
        self.assertIn("13/02/2024", mdy_result.stderr.decode("utf-8"))
        self.assertFalse(mdy_output.exists())

        dmy_output = self.tmpdir / "cleaned_ambiguity_dmy.csv"
        dmy_result = self.run_cleaner(input_path, dmy_output, order="dmy")
        self.assertEqual(dmy_result.returncode, 0)
        self.assertEqual(dmy_result.stderr, b"")
        self.assertEqual(
            self.read_output_records(dmy_output),
            [DATE_HEADER, ["2024-02-13", "ambiguous"]],
        )

    # (label, order value or bare flag, rule, stderr fragments).
    INVALID_ORDER_SCENARIOS = [
        ("missing_value", None, "normalize-date",
         ["--date-order", "expected one argument"]),
        ("uppercase_dmy", "DMY", "normalize-date",
         ["--date-order", "invalid choice", "DMY"]),
        ("unknown_order", "ymd", "normalize-date",
         ["--date-order", "invalid choice", "ymd"]),
        ("with_trim_mdy", "mdy", "trim",
         ["--date-order can only be used with --rule normalize-date"]),
        ("with_trim_dmy", "dmy", "trim",
         ["--date-order can only be used with --rule normalize-date"]),
        ("with_normalize_null", "mdy", "normalize-null",
         ["--date-order can only be used with --rule normalize-date"]),
    ]

    def assert_invalid_order_rejected(self, rows, *, tag, column="due_date"):
        input_path = self.write_input(rows, tag=tag)
        for label, order, rule, fragments in self.INVALID_ORDER_SCENARIOS:
            with self.subTest(label=label):
                output_path = self.tmpdir / f"cleaned_{tag}_{label}.csv"

                result = self.run_cleaner(
                    input_path, output_path, order=order, rule=rule,
                    column=column,
                )

                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, b"")
                stderr_text = result.stderr.decode("utf-8")
                for fragment in fragments:
                    self.assertIn(fragment, stderr_text)
                self.assertNotIn("Traceback", stderr_text)
                # Parameter validation precedes every export.
                self.assertFalse(output_path.exists())

    def test_invalid_order_rejected_on_data_file(self):
        self.assert_invalid_order_rejected(
            self.ORDER_ROWS, tag="order_bad_data"
        )

    def test_invalid_order_rejected_on_header_only_file(self):
        # A perfectly valid header-only input must not make any invalid
        # parameter combination acceptable.
        self.assert_invalid_order_rejected(
            [DATE_HEADER], tag="order_bad_header"
        )

    def test_valid_order_on_header_only_exports_header(self):
        input_path = self.write_input([DATE_HEADER], tag="order_header_ok")
        output_path = self.tmpdir / "cleaned_order_header_ok.csv"

        result = self.run_cleaner(input_path, output_path, order="mdy")

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


class DryRunDateOrderTests(unittest.TestCase):
    """Regression coverage for --dry-run combined with --date-order.

    The date-order export and the default-order preview are each covered
    elsewhere; these tests pin only the existing behavior of the
    combination, going through the documented public CLI with small
    UTF-8 CSV files in a private temporary directory. Results are judged
    on parsed CSV rows and the parsed JSON object, so equivalent quoting
    styles and JSON key order are irrelevant. The preview must convert
    and validate dates under the chosen (or defaulted) order, print the
    same JSON content a real export would, and create no file or
    directory while leaving the input bytes untouched.
    """

    # due_date,note header plus four data records. The ambiguous
    # 05/06/2024 is month/day under mdy but day/month under dmy; the
    # YYYY/MM/DD leap day stays year-month-day under either order; the
    # ISO date and the empty cell never change. The first record's note
    # carries a quoted real newline, which must not disturb record
    # numbering (the header is record 1).
    PREVIEW_ORDER_ROWS = [
        DATE_HEADER,
        ["05/06/2024", 'first note\nstill first'],  # record 2, quoted newline
        ["2024/02/29", "second, note"],             # record 3
        ["2024-01-01", 'third "note"'],             # record 4: already ISO
        ["", "fourth note"],                        # record 5: already empty
    ]
    ORDER_DATES_MDY = ["2024-05-06", "2024-02-29", "2024-01-01", ""]
    ORDER_DATES_DMY = ["2024-06-05", "2024-02-29", "2024-01-01", ""]

    @staticmethod
    def changes_for(expected_after_first):
        # Only records 2 (the ambiguous slash date) and 3 (the
        # YYYY/MM/DD leap day) change; the ISO and empty cells do not.
        return [
            {"record": 2, "column": "due_date",
             "before": "05/06/2024", "after": expected_after_first},
            {"record": 3, "column": "due_date",
             "before": "2024/02/29", "after": "2024-02-29"},
        ]

    # Second sample: the first record is cleanable under mdy and again
    # carries the quoted newline, so the first impossible date sits at
    # record 3 (13/02/2024 is month 13 under mdy); 02/30/2024 at record
    # 4 must never be reported because the run aborts at the first
    # failure.
    INVALID_ORDER_ROWS = [
        DATE_HEADER,
        ["05/06/2024", 'first note\nstill first'],
        ["13/02/2024", "second note"],
        ["02/30/2024", "third note"],
    ]

    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.tmpdir = Path(self._tempdir.name)

    def write_input(self, rows, *, tag):
        data = encode_csv(rows, bom=False)
        path = self.tmpdir / f"input_{tag}.csv"
        path.write_bytes(data)
        return path, data

    def run_cleaner(self, input_path, output_path, *, order="OMITTED",
                    dry_run, include_changes=False):
        # order="OMITTED" means --date-order is not passed at all.
        argv = [
            sys.executable, str(SCRIPT_PATH),
            "--input", str(input_path),
            "--output", str(output_path),
            "--column", "due_date",
            "--rule", "normalize-date",
        ]
        if order != "OMITTED":
            argv.extend(["--date-order", order])
        if include_changes:
            argv.append("--include-changes")
        if dry_run:
            argv.append("--dry-run")
        return subprocess.run(
            argv, cwd=str(self.tmpdir), capture_output=True
        )

    def read_output_records(self, path):
        # Plain utf-8 (not utf-8-sig) so a stray BOM would surface.
        with open(path, "r", encoding="utf-8", newline="") as outfile:
            return list(csv.reader(outfile))

    def assert_workspace_holds_only(self, names):
        self.assertEqual(
            sorted(p.name for p in self.tmpdir.iterdir()), sorted(names)
        )

    def test_preview_summary_follows_the_chosen_or_default_order(self):
        # mdy, explicit dmy and the omitted option (documented dmy
        # default) each preview with exit 0, empty stderr and rows 4 /
        # changed_cells 2, with and without --include-changes. Without
        # the switch the summary has no changes key; with it only
        # records 2 and 3 appear in record order with the column name,
        # the raw before string and the chosen order's after value. The
        # preview writes nothing, the preview output sits below a
        # nonexistent parent directory (which must not be created), and
        # the input bytes stay unchanged.
        input_path, original_bytes = self.write_input(
            self.PREVIEW_ORDER_ROWS, tag="order_preview"
        )
        missing_dir = self.tmpdir / "nodir"
        preview_path = missing_dir / "cleaned_preview.csv"
        self.assertFalse(missing_dir.exists())

        scenarios = [
            ("mdy", "mdy", "2024-05-06"),
            ("dmy", "dmy", "2024-06-05"),
            ("omitted", "OMITTED", "2024-06-05"),
        ]
        for label, order, first_after in scenarios:
            expected_changes = self.changes_for(first_after)
            for include_changes in (False, True):
                with self.subTest(
                    order=label, include_changes=include_changes
                ):
                    result = self.run_cleaner(
                        input_path, preview_path, order=order, dry_run=True,
                        include_changes=include_changes,
                    )

                    self.assertEqual(result.returncode, 0)
                    self.assertEqual(result.stderr, b"")
                    # stdout must consist of exactly one JSON object and
                    # nothing else; json.loads rejects trailing
                    # non-whitespace.
                    summary = json.loads(result.stdout.decode("utf-8"))
                    expected = {"rows": 4, "changed_cells": 2}
                    if include_changes:
                        expected["changes"] = expected_changes
                    self.assertEqual(summary, expected)
                    if include_changes:
                        # Detail length equals the changed-cell count and
                        # the entries stay in record order.
                        self.assertEqual(
                            len(summary["changes"]),
                            summary["changed_cells"],
                        )
                        self.assertEqual(
                            [entry["record"] for entry in summary["changes"]],
                            [2, 3],
                        )
                    else:
                        self.assertNotIn("changes", summary)
                    # A successful preview creates neither the output
                    # file nor the missing parent directory...
                    self.assertFalse(preview_path.exists())
                    self.assertFalse(missing_dir.exists())
                    # ...and leaves the input bytes exactly as written.
                    self.assertEqual(
                        input_path.read_bytes(), original_bytes
                    )

        self.assert_workspace_holds_only([input_path.name])

    def test_preview_json_matches_a_real_export_under_each_order(self):
        # With identical cleaning parameters (order and details switch),
        # the preview and a real export into another valid fresh path
        # print the same JSON content, compared by parsed content rather
        # than key order. The export keeps the header, every note
        # (including the quoted newline, comma and double quotes) and
        # the record order, with the due_date column normalized under
        # the chosen order; the preview path and its missing parent
        # never appear and the input bytes stay unchanged.
        scenarios = [
            ("mdy", "mdy", self.ORDER_DATES_MDY, "2024-05-06"),
            ("dmy", "dmy", self.ORDER_DATES_DMY, "2024-06-05"),
            ("omitted", "OMITTED", self.ORDER_DATES_DMY, "2024-06-05"),
        ]
        for label, order, expected_dates, first_after in scenarios:
            input_path, original_bytes = self.write_input(
                self.PREVIEW_ORDER_ROWS, tag=f"order_preview_export_{label}"
            )
            expected_changes = self.changes_for(first_after)
            for include_changes in (False, True):
                with self.subTest(
                    order=label, include_changes=include_changes
                ):
                    detail = "with" if include_changes else "without"
                    preview_path = (
                        self.tmpdir / "nodir" / f"preview_{label}_{detail}.csv"
                    )
                    export_path = (
                        self.tmpdir / f"cleaned_export_{label}_{detail}.csv"
                    )
                    self.assertFalse(preview_path.exists())
                    self.assertFalse(export_path.exists())

                    preview = self.run_cleaner(
                        input_path, preview_path, order=order, dry_run=True,
                        include_changes=include_changes,
                    )
                    export = self.run_cleaner(
                        input_path, export_path, order=order, dry_run=False,
                        include_changes=include_changes,
                    )

                    self.assertEqual(preview.returncode, 0)
                    self.assertEqual(preview.stderr, b"")
                    self.assertEqual(export.returncode, 0)
                    self.assertEqual(export.stderr, b"")
                    # Same cleaning parameters -> same JSON content.
                    preview_summary = json.loads(
                        preview.stdout.decode("utf-8")
                    )
                    export_summary = json.loads(
                        export.stdout.decode("utf-8")
                    )
                    self.assertEqual(preview_summary, export_summary)
                    expected = {"rows": 4, "changed_cells": 2}
                    if include_changes:
                        expected["changes"] = expected_changes
                    self.assertEqual(export_summary, expected)

                    # The preview path (below a missing parent) stays
                    # absent and no directory is created.
                    self.assertFalse(preview_path.exists())
                    self.assertFalse(preview_path.parent.exists())
                    # The real export exists, is BOM-free and preserves
                    # the header, record order and all notes while
                    # carrying the order's normalized dates.
                    self.assertTrue(export_path.exists())
                    self.assertFalse(
                        export_path.read_bytes().startswith(codecs.BOM_UTF8)
                    )
                    output_rows = self.read_output_records(export_path)
                    self.assertEqual(output_rows[0], DATE_HEADER)
                    self.assertEqual(len(output_rows), 5)
                    self.assertEqual(
                        [row[0] for row in output_rows[1:]], expected_dates
                    )
                    self.assertEqual(
                        [row[1] for row in output_rows],
                        [row[1] for row in self.PREVIEW_ORDER_ROWS],
                    )
                    self.assertEqual(
                        input_path.read_bytes(), original_bytes
                    )

    def test_mdy_preview_still_validates_dates_and_reports_first_only(self):
        # Choosing an order must not bypass date validation. Under mdy
        # the 13/02/2024 at record 3 is month 13 and is invalid; with
        # and without --include-changes the preview exits 2 with stdout
        # exactly empty (so neither a summary nor a changes detail is
        # printed) and stderr locating only due_date at record 3 with
        # the raw value 13/02/2024: no Python traceback and no report of
        # the later 02/30/2024 record. No file or directory is created
        # and the input bytes stay unchanged.
        input_path, original_bytes = self.write_input(
            self.INVALID_ORDER_ROWS, tag="order_preview_invalid"
        )
        missing_dir = self.tmpdir / "nodir"
        preview_path = missing_dir / "cleaned_preview_invalid.csv"
        self.assertFalse(missing_dir.exists())

        for include_changes in (False, True):
            with self.subTest(include_changes=include_changes):
                result = self.run_cleaner(
                    input_path, preview_path, order="mdy", dry_run=True,
                    include_changes=include_changes,
                )

                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, b"")
                stderr_text = result.stderr.decode("utf-8")
                self.assertIn("invalid date", stderr_text)
                self.assertIn("due_date", stderr_text)
                self.assertIn("record 3", stderr_text)
                # The message quotes the first offending value verbatim.
                self.assertIn("13/02/2024", stderr_text)
                # Only the first invalid date is reported; the later
                # February-30 record must not appear anywhere.
                self.assertNotIn("record 4", stderr_text)
                self.assertNotIn("02/30/2024", stderr_text)
                self.assertNotIn("Traceback", stderr_text)
                self.assertFalse(preview_path.exists())
                self.assertFalse(missing_dir.exists())
                self.assertEqual(input_path.read_bytes(), original_bytes)

        self.assert_workspace_holds_only([input_path.name])


class NormalizeWhitespaceCliTests(unittest.TestCase):
    """Coverage for the normalize-whitespace rule.

    Every test goes through the documented public CLI against small CSV
    files in a private temporary directory; results are judged on parsed
    CSV fields and the parsed JSON object, so equivalent quoting styles
    and JSON key order are irrelevant.
    """

    # The acceptance sample: name,note header plus four data records.
    # The names parse as " Alice  Smith " (internal runs collapse, ends
    # trimmed), a string holding only a tab and an ideographic space
    # (U+3000, whitespace under str.isspace, so the cell becomes empty),
    # "Bob Lee" (already single-spaced, not a change) and an empty
    # string. The first record's note carries a quoted real newline,
    # which must not disturb record numbering (the header is record 1).
    WS_ROWS = [
        HEADER,
        [" Alice  Smith ", "first line\nstill first"],
        ["\t　", "x,y"],          # tab + U+3000: whitespace-only -> ""
        ["Bob Lee", 'he said "ok"'],
        ["", "plain"],
    ]
    WS_EXPECTED_NAMES = ["Alice Smith", "", "Bob Lee", ""]
    WS_EXPECTED_CHANGES = [
        {"record": 2, "column": "name",
         "before": " Alice  Smith ", "after": "Alice Smith"},
        {"record": 3, "column": "name",
         "before": "\t　", "after": ""},
    ]

    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.tmpdir = Path(self._tempdir.name)

    def write_input(self, rows, *, bom, tag):
        data = encode_csv(rows, bom=bom)
        path = self.tmpdir / f"input_{tag}.csv"
        path.write_bytes(data)
        return path, data

    def run_cleaner(self, input_path, output_path, *,
                    include_changes=False, dry_run=False, extra_args=(),
                    column="name"):
        argv = [
            sys.executable,
            str(SCRIPT_PATH),
            "--input", str(input_path),
            "--output", str(output_path),
            "--column", column,
            "--rule", "normalize-whitespace",
        ]
        if include_changes:
            argv.append("--include-changes")
        if dry_run:
            argv.append("--dry-run")
        argv.extend(extra_args)
        return subprocess.run(
            argv, cwd=str(self.tmpdir), capture_output=True
        )

    def read_output_records(self, path):
        # Plain utf-8 (not utf-8-sig) so a stray BOM would surface as content.
        with open(path, "r", encoding="utf-8", newline="") as outfile:
            return list(csv.reader(outfile))

    def assert_workspace_holds_only(self, names):
        self.assertEqual(
            sorted(p.name for p in self.tmpdir.iterdir()), sorted(names)
        )

    def test_export_with_and_without_bom(self):
        for bom in (False, True):
            with self.subTest(bom=bom):
                tag = "ws_bom" if bom else "ws_nobom"
                input_path, original_bytes = self.write_input(
                    self.WS_ROWS, bom=bom, tag=tag
                )
                output_path = self.tmpdir / f"cleaned_{tag}.csv"
                self.assertFalse(output_path.exists())

                result = self.run_cleaner(input_path, output_path)

                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, b"")
                # stdout must consist of exactly one JSON object and
                # nothing else; json.loads rejects trailing non-whitespace.
                self.assertEqual(
                    json.loads(result.stdout.decode("utf-8")),
                    {"rows": 4, "changed_cells": 2},
                )

                self.assertTrue(output_path.exists())
                raw_output = output_path.read_bytes()
                self.assertFalse(raw_output.startswith(codecs.BOM_UTF8))
                output_rows = self.read_output_records(output_path)
                # Header and record order are unchanged.
                self.assertEqual(output_rows[0], HEADER)
                self.assertEqual(len(output_rows), 5)
                self.assertEqual(
                    [row[0] for row in output_rows[1:]],
                    self.WS_EXPECTED_NAMES,
                )
                # The note column is never cleaned: the embedded newline,
                # comma and double quotes round-trip exactly.
                self.assertEqual(
                    [row[1] for row in output_rows],
                    [row[1] for row in self.WS_ROWS],
                )
                # The input file is opened read-only: exact bytes remain.
                self.assertEqual(input_path.read_bytes(), original_bytes)

    def test_changes_detail_lists_records_2_and_3(self):
        # With --include-changes only the two changed cells appear, in
        # record order, with the parsed original values (including the
        # tab and the ideographic space) preserved in before. The quoted
        # newline in record 2's note does not shift the record numbers.
        input_path, original_bytes = self.write_input(
            self.WS_ROWS, bom=False, tag="ws_changes"
        )
        output_path = self.tmpdir / "cleaned_ws_changes.csv"

        result = self.run_cleaner(
            input_path, output_path, include_changes=True
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        summary = json.loads(result.stdout.decode("utf-8"))
        self.assertEqual(
            summary,
            {"rows": 4, "changed_cells": 2,
             "changes": self.WS_EXPECTED_CHANGES},
        )
        self.assertEqual(
            len(summary["changes"]), summary["changed_cells"]
        )
        self.assertEqual(input_path.read_bytes(), original_bytes)

    def test_whitespace_only_cells_and_zero_width_space(self):
        # Tabs, carriage returns, newlines and ideographic spaces are all
        # whitespace under str.isspace: a whitespace-only cell becomes
        # empty and internal runs collapse to one ASCII space. The
        # zero-width space U+200B is not whitespace, so it survives
        # verbatim, as do NULL / N/A / date text (whitespace only, no
        # other conversion).
        cells = [
            ("\t\r\n　", ""),                     # whitespace-only -> ""
            ("a\tb\rc\nd　e", "a b c d e"),       # runs -> one space
            ("​", "​"),                     # U+200B kept
            ("　N/A　", "N/A"),                   # marker text kept as text
            (" 2024-02-29 ", "2024-02-29"),       # date text kept as text
            ("NULL", "NULL"),                     # already clean: no change
        ]
        rows = [HEADER] + [[value, "note"] for value, _ in cells]
        input_path, original_bytes = self.write_input(
            rows, bom=False, tag="ws_boundaries"
        )
        output_path = self.tmpdir / "cleaned_ws_boundaries.csv"

        result = self.run_cleaner(input_path, output_path)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(
            json.loads(result.stdout.decode("utf-8")),
            {"rows": 6, "changed_cells": 4},
        )
        self.assertEqual(
            [row[0] for row in self.read_output_records(output_path)[1:]],
            [expected for _, expected in cells],
        )
        self.assertEqual(input_path.read_bytes(), original_bytes)

    def test_dry_run_preview_matches_export_and_creates_nothing(self):
        # The preview prints the identical summary as a real export
        # (with and without --include-changes) but creates neither the
        # output file nor its missing parent directory.
        input_path, original_bytes = self.write_input(
            self.WS_ROWS, bom=False, tag="ws_preview"
        )
        missing_dir = self.tmpdir / "nodir"

        for include_changes in (False, True):
            with self.subTest(include_changes=include_changes):
                tag = "with" if include_changes else "without"
                preview_path = missing_dir / f"preview_{tag}.csv"
                export_path = self.tmpdir / f"cleaned_export_{tag}.csv"

                preview = self.run_cleaner(
                    input_path, preview_path, dry_run=True,
                    include_changes=include_changes,
                )
                export = self.run_cleaner(
                    input_path, export_path,
                    include_changes=include_changes,
                )

                self.assertEqual(preview.returncode, 0)
                self.assertEqual(preview.stderr, b"")
                self.assertEqual(export.returncode, 0)
                self.assertEqual(export.stderr, b"")
                self.assertEqual(preview.stdout, export.stdout)
                summary = json.loads(preview.stdout.decode("utf-8"))
                expected = {"rows": 4, "changed_cells": 2}
                if include_changes:
                    expected["changes"] = self.WS_EXPECTED_CHANGES
                self.assertEqual(summary, expected)
                self.assertFalse(preview_path.exists())
                self.assertFalse(missing_dir.exists())
                self.assertEqual(
                    [row[0] for row in
                     self.read_output_records(export_path)[1:]],
                    self.WS_EXPECTED_NAMES,
                )
                self.assertEqual(input_path.read_bytes(), original_bytes)

        self.assert_workspace_holds_only(
            [input_path.name,
             "cleaned_export_with.csv", "cleaned_export_without.csv"]
        )

    def test_header_only_reports_zero_counts(self):
        input_path, original_bytes = self.write_input(
            [HEADER], bom=False, tag="ws_header_only"
        )
        output_path = self.tmpdir / "cleaned_ws_header_only.csv"

        for include_changes in (False, True):
            with self.subTest(include_changes=include_changes):
                result = self.run_cleaner(
                    input_path, output_path, include_changes=include_changes
                )

                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, b"")
                expected = {"rows": 0, "changed_cells": 0}
                if include_changes:
                    expected["changes"] = []
                self.assertEqual(
                    json.loads(result.stdout.decode("utf-8")), expected
                )
                self.assertEqual(
                    self.read_output_records(output_path), [HEADER]
                )
                output_path.unlink()
                self.assertEqual(input_path.read_bytes(), original_bytes)

    # (label, extra args, stderr fragments).
    INCOMPATIBLE_SCENARIOS = [
        ("null_marker", ["--null-marker", "MISSING"],
         ["--null-marker can only be used with --rule normalize-null"]),
        ("date_order", ["--date-order", "mdy"],
         ["--date-order can only be used with --rule normalize-date"]),
    ]

    def assert_incompatible_options_rejected(self, rows, *, tag):
        input_path, original_bytes = self.write_input(
            rows, bom=False, tag=tag
        )
        for label, extra_args, fragments in self.INCOMPATIBLE_SCENARIOS:
            for include_changes in (False, True):
                with self.subTest(label=label,
                                  include_changes=include_changes):
                    output_path = (
                        self.tmpdir / f"cleaned_{tag}_{label}.csv"
                    )
                    self.assertFalse(output_path.exists())

                    result = self.run_cleaner(
                        input_path, output_path,
                        include_changes=include_changes,
                        extra_args=extra_args,
                    )

                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stdout, b"")
                    stderr_text = result.stderr.decode("utf-8")
                    for fragment in fragments:
                        self.assertIn(fragment, stderr_text)
                    self.assertNotIn("Traceback", stderr_text)
                    self.assertFalse(output_path.exists())
                    self.assertEqual(
                        input_path.read_bytes(), original_bytes
                    )

    def test_incompatible_options_rejected_on_data_file(self):
        self.assert_incompatible_options_rejected(
            self.WS_ROWS, tag="ws_bad_data"
        )

    def test_incompatible_options_rejected_on_header_only_file(self):
        # A perfectly valid header-only input must not make the invalid
        # parameter combinations acceptable.
        self.assert_incompatible_options_rejected(
            [HEADER], tag="ws_bad_header"
        )


class EmptyLineBoundaryTests(unittest.TestCase):
    """Empty physical lines and empty fields at the CSV record boundary.

    Every run goes through the public CLI with --rule trim on the name
    column and --include-changes, in both export and --dry-run modes,
    against raw-byte inputs covering LF and CRLF record separators with
    and without a UTF-8 BOM.
    """

    # Failure sample: record 2's quoted note is two-line text with a real
    # newline; the completely empty physical line after it parses as
    # record 3 with zero fields (the quoted newline does not advance the
    # record number).
    MID_FILE_EMPTY_LINE = [
        "name,note",
        '" Alice ","two\nlines"',
        "",
        "Bob,z",
    ]

    # Failure sample: an empty physical line before anything else, so the
    # first record has zero fields and there is no header record at all,
    # even though a normal header follows.
    LEADING_EMPTY_LINE = [
        "",
        "name,note",
        "Bob,z",
    ]

    # Success control: the blank physical line sits inside record 2's
    # quoted note (two consecutive real newlines), record 3 is a bare
    # comma meaning two empty fields, and record 4 is ordinary. None of
    # these may be rejected or skipped.
    SUCCESS_LINES = [
        "name,note",
        '" Alice ","first\n\nsecond"',
        ",",
        "Bob,z",
    ]
    SUCCESS_RECORDS = [
        HEADER,
        ["Alice", "first\n\nsecond"],
        ["", ""],
        ["Bob", "z"],
    ]
    SUCCESS_SUMMARY = {
        "rows": 3,
        "changed_cells": 1,
        "changes": [
            {"record": 2, "column": "name",
             "before": " Alice ", "after": "Alice"},
        ],
    }

    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.tmpdir = Path(self._tempdir.name)

    def write_raw_input(self, data, *, tag):
        """Write arbitrary raw bytes as an input file and report its path."""
        path = self.tmpdir / f"input_{tag}.csv"
        path.write_bytes(data)
        return path, data

    def run_cleaner(self, input_path, output_path, *, dry_run):
        argv = [
            sys.executable,
            str(SCRIPT_PATH),
            "--input", str(input_path),
            "--output", str(output_path),
            "--column", "name",
            "--rule", "trim",
            "--include-changes",
        ]
        if dry_run:
            argv.append("--dry-run")
        return subprocess.run(
            argv,
            cwd=str(self.tmpdir),
            capture_output=True,
        )

    def read_output_records(self, path):
        # Plain utf-8 (not utf-8-sig) so a stray BOM would surface as content.
        with open(path, "r", encoding="utf-8", newline="") as outfile:
            return list(csv.reader(outfile))

    def existing_names(self):
        return {p.name for p in self.tmpdir.iterdir()}

    def assert_fails_in_both_modes(self, lines, *, fragments, tag_prefix):
        for newline in ("\n", "\r\n"):
            for bom in (False, True):
                for dry_run in (False, True):
                    tag = "%s_%s_%s_%s" % (
                        tag_prefix,
                        "crlf" if newline == "\r\n" else "lf",
                        "bom" if bom else "nobom",
                        "dry" if dry_run else "export",
                    )
                    with self.subTest(newline=repr(newline), bom=bom,
                                      dry_run=dry_run):
                        data = encode_lines(lines, newline=newline, bom=bom)
                        input_path, original_bytes = self.write_raw_input(
                            data, tag=tag
                        )
                        output_path = self.tmpdir / f"cleaned_{tag}.csv"
                        self.assertFalse(output_path.exists())
                        before = self.existing_names()

                        result = self.run_cleaner(
                            input_path, output_path, dry_run=dry_run
                        )

                        self.assertEqual(result.returncode, 2)
                        self.assertEqual(result.stdout, b"")
                        stderr_text = result.stderr.decode("utf-8")
                        for fragment in fragments:
                            self.assertIn(fragment, stderr_text)
                        self.assertNotIn("Traceback", stderr_text)
                        # No output file and no other new file appears, so
                        # no cleaned record can be left behind anywhere.
                        self.assertFalse(output_path.exists())
                        self.assertEqual(self.existing_names(), before)
                        # The input file is opened read-only: bytes remain.
                        self.assertEqual(
                            input_path.read_bytes(), original_bytes
                        )

    def test_mid_file_empty_line_is_zero_field_record_3(self):
        self.assert_fails_in_both_modes(
            self.MID_FILE_EMPTY_LINE,
            fragments=["record 3", "0 field(s)", "expected 2"],
            tag_prefix="midempty",
        )

    def test_leading_empty_line_means_no_header_record(self):
        self.assert_fails_in_both_modes(
            self.LEADING_EMPTY_LINE,
            fragments=["input is empty", "no header record"],
            tag_prefix="leadempty",
        )

    def test_quoted_blank_line_and_empty_fields_are_kept(self):
        for newline in ("\n", "\r\n"):
            for bom in (False, True):
                tag = "keep_%s_%s" % (
                    "crlf" if newline == "\r\n" else "lf",
                    "bom" if bom else "nobom",
                )
                with self.subTest(newline=repr(newline), bom=bom):
                    data = encode_lines(
                        self.SUCCESS_LINES, newline=newline, bom=bom
                    )
                    input_path, original_bytes = self.write_raw_input(
                        data, tag=tag
                    )
                    output_path = self.tmpdir / f"cleaned_{tag}.csv"
                    self.assertFalse(output_path.exists())

                    result = self.run_cleaner(
                        input_path, output_path, dry_run=False
                    )

                    self.assertEqual(result.returncode, 0)
                    self.assertEqual(result.stderr, b"")
                    # The whole stdout parses as one JSON object, compared
                    # by content rather than key order.
                    summary = json.loads(result.stdout.decode("utf-8"))
                    self.assertEqual(summary, self.SUCCESS_SUMMARY)

                    self.assertTrue(output_path.exists())
                    raw_output = output_path.read_bytes()
                    self.assertFalse(raw_output.startswith(codecs.BOM_UTF8))
                    # Parsed records match regardless of the equivalent
                    # quoting style or record separator the writer picks;
                    # the note's real newlines survive inside record 2.
                    self.assertEqual(
                        self.read_output_records(output_path),
                        self.SUCCESS_RECORDS,
                    )
                    self.assertEqual(
                        input_path.read_bytes(), original_bytes
                    )

                    # The --dry-run preview of the same input prints the
                    # identical JSON content and creates nothing, even
                    # with the output below a missing parent directory.
                    preview_parent = self.tmpdir / f"missing_{tag}"
                    preview_path = preview_parent / f"cleaned_{tag}.csv"
                    self.assertFalse(preview_parent.exists())
                    before = self.existing_names()

                    preview = self.run_cleaner(
                        input_path, preview_path, dry_run=True
                    )

                    self.assertEqual(preview.returncode, 0)
                    self.assertEqual(preview.stderr, b"")
                    self.assertEqual(
                        json.loads(preview.stdout.decode("utf-8")),
                        summary,
                    )
                    self.assertFalse(preview_path.exists())
                    self.assertFalse(preview_parent.exists())
                    self.assertEqual(self.existing_names(), before)
                    self.assertEqual(
                        input_path.read_bytes(), original_bytes
                    )


class SemicolonDelimiterCliTests(unittest.TestCase):
    """Regression coverage for the explicit --delimiter semicolon switch.

    Every test goes through the documented public CLI against small UTF-8
    CSV files in a private temporary directory: no external files or
    network. Results are judged on parsed CSV fields and the parsed JSON
    object, so equivalent quoting styles, record separators and JSON key
    order are irrelevant. The chosen delimiter must be used both to read
    the input and to write the export and must never be guessed from the
    file contents; omitting the option keeps the default comma behavior.
    """

    # Acceptance sample serialized with semicolon field separators. The
    # first note embeds a literal semicolon, a double quote and a quoted
    # real newline, so it can only round-trip when the same delimiter is
    # used for reading and writing and the quote handling stays intact.
    SAMPLE_ROWS = [
        ["name", "note"],
        [" Alice ", 'x;y"z\nnext'],
        ["   ", "ok"],                 # three ASCII spaces trim to empty
        ["Bob", "z"],
    ]
    EXPECTED_ROWS = [
        ["name", "note"],
        ["Alice", 'x;y"z\nnext'],
        ["", "ok"],
        ["Bob", "z"],
    ]
    EXPECTED_SUMMARY = {
        "rows": 3,
        "changed_cells": 2,
        "changes": [
            {"record": 2, "column": "name",
             "before": " Alice ", "after": "Alice"},
            {"record": 3, "column": "name",
             "before": "   ", "after": ""},
        ],
    }
    # Smallest possible semicolon file for the no-guessing check: the
    # header plus one data record.
    TWO_ROWS = [
        ["name", "note"],
        ["Bob", "z"],
    ]

    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.tmpdir = Path(self._tempdir.name)

    def write_input(self, rows, *, bom, tag, field_delimiter=";"):
        """Serialize rows with the given field delimiter, as UTF-8 bytes."""
        buffer = io.StringIO()
        csv.writer(buffer, delimiter=field_delimiter).writerows(rows)
        encoding = "utf-8-sig" if bom else "utf-8"
        data = buffer.getvalue().encode(encoding)
        path = self.tmpdir / f"input_{tag}.csv"
        path.write_bytes(data)
        return path, data

    def run_cleaner(self, input_path, output_path, *, delimiter="OMITTED",
                    dry_run=False, include_changes=False):
        # delimiter="OMITTED" means --delimiter is not passed at all
        # (the documented comma default); None means the bare flag with
        # no following value.
        argv = [
            sys.executable, str(SCRIPT_PATH),
            "--input", str(input_path),
            "--output", str(output_path),
            "--column", "name",
            "--rule", "trim",
        ]
        if delimiter != "OMITTED":
            argv.append("--delimiter")
            if delimiter is not None:
                argv.append(delimiter)
        if include_changes:
            argv.append("--include-changes")
        if dry_run:
            argv.append("--dry-run")
        return subprocess.run(
            argv, cwd=str(self.tmpdir), capture_output=True
        )

    def read_output_records(self, path, field_delimiter=";"):
        # Plain utf-8 (not utf-8-sig) so a stray BOM would surface as
        # content.
        with open(path, "r", encoding="utf-8", newline="") as outfile:
            return list(csv.reader(outfile, delimiter=field_delimiter))

    def workspace_names(self):
        return sorted(p.name for p in self.tmpdir.iterdir())

    def test_semicolon_used_for_read_and_export_with_and_without_bom(self):
        for bom in (False, True):
            with self.subTest(bom=bom):
                tag = "semi_bom" if bom else "semi_nobom"
                input_path, original_bytes = self.write_input(
                    self.SAMPLE_ROWS, bom=bom, tag=tag
                )
                output_path = self.tmpdir / f"cleaned_{tag}.csv"
                self.assertFalse(output_path.exists())

                result = self.run_cleaner(
                    input_path, output_path,
                    delimiter="semicolon", include_changes=True,
                )

                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, b"")
                # The whole stdout must parse as one JSON object and
                # nothing else; json.loads rejects trailing junk.
                summary = json.loads(result.stdout.decode("utf-8"))
                self.assertEqual(summary, self.EXPECTED_SUMMARY)

                self.assertTrue(output_path.exists())
                raw_output = output_path.read_bytes()
                # The export is BOM-free UTF-8 even when the input had
                # a BOM.
                self.assertFalse(raw_output.startswith(codecs.BOM_UTF8))
                # Read back with the semicolon dialect: the header,
                # record order and every note value survive, including
                # the embedded semicolon, double quote and real newline.
                self.assertEqual(
                    self.read_output_records(output_path),
                    self.EXPECTED_ROWS,
                )
                # The same bytes parsed as a comma CSV collapse to one
                # field per record, proving the export really uses
                # semicolons rather than the comma default.
                with open(
                    output_path, "r", encoding="utf-8", newline=""
                ) as outfile:
                    comma_rows = list(csv.reader(outfile))
                self.assertTrue(
                    all(len(row) == 1 for row in comma_rows), comma_rows
                )

                # The input file is opened read-only: exact bytes remain.
                self.assertEqual(input_path.read_bytes(), original_bytes)

    def test_semicolon_dry_run_matches_export_and_creates_nothing(self):
        for bom in (False, True):
            with self.subTest(bom=bom):
                tag = "semi_dry_bom" if bom else "semi_dry_nobom"
                input_path, original_bytes = self.write_input(
                    self.SAMPLE_ROWS, bom=bom, tag=tag
                )
                # Reference: a real export of the same input.
                export_path = self.tmpdir / f"export_{tag}.csv"
                export_result = self.run_cleaner(
                    input_path, export_path,
                    delimiter="semicolon", include_changes=True,
                )
                self.assertEqual(export_result.returncode, 0)
                reference_summary = json.loads(
                    export_result.stdout.decode("utf-8")
                )

                # The preview output sits below a parent directory that
                # does not exist.
                missing_dir = self.tmpdir / f"nodir_{tag}"
                preview_path = missing_dir / "cleaned.csv"
                self.assertFalse(missing_dir.exists())
                self.assertFalse(preview_path.exists())
                # Snapshot after the reference export: the preview must
                # not add even a directory or stray file on top of it.
                before_names = self.workspace_names()

                result = self.run_cleaner(
                    input_path, preview_path,
                    delimiter="semicolon", dry_run=True,
                    include_changes=True,
                )

                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, b"")
                # Same JSON content as the real export, compared by
                # parsed content rather than key order or spacing.
                self.assertEqual(
                    json.loads(result.stdout.decode("utf-8")),
                    reference_summary,
                )
                # Neither the file nor its missing parent is created,
                # and nothing else appears in the workspace.
                self.assertFalse(preview_path.exists())
                self.assertFalse(missing_dir.exists())
                self.assertEqual(self.workspace_names(), before_names)
                self.assertEqual(input_path.read_bytes(), original_bytes)

    def test_delimiter_is_never_guessed_from_file_contents(self):
        # A semicolon-separated file with the option omitted must be
        # read with the comma default, so the header is a single column
        # and "name" is not found -- nothing is sniffed from the data.
        input_path, original_bytes = self.write_input(
            self.TWO_ROWS, bom=False, tag="guess"
        )
        output_path = self.tmpdir / "cleaned_guess.csv"
        self.assertFalse(output_path.exists())

        result = self.run_cleaner(input_path, output_path)

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        stderr_text = result.stderr.decode("utf-8")
        self.assertIn("column not found", stderr_text)
        self.assertIn("name", stderr_text)
        self.assertNotIn("Traceback", stderr_text)
        self.assertFalse(output_path.exists())
        self.assertEqual(self.workspace_names(), [input_path.name])
        self.assertEqual(input_path.read_bytes(), original_bytes)

    def test_invalid_delimiter_values_rejected_on_data_and_header_only(self):
        # None: the bare --delimiter flag with no following value;
        # "": an explicit empty string; "Semicolon": the lowercase
        # choice names are case-sensitive. argparse must reject each
        # one (exit 2) before any file is touched, on both a data file
        # and a header-only file.
        cases = [
            (None, "expected one argument", None),
            ("", "invalid choice", "''"),
            ("Semicolon", "invalid choice", "Semicolon"),
        ]
        for sample_name, rows in (
            ("data", self.TWO_ROWS),
            ("header_only", [["name", "note"]]),
        ):
            for value, reason, echoed in cases:
                with self.subTest(sample=sample_name, value=value):
                    tag = "delim_%s_%s" % (
                        sample_name,
                        {None: "missing", "": "empty",
                         "Semicolon": "capitalized"}[value],
                    )
                    input_path, original_bytes = self.write_input(
                        rows, bom=False, tag=tag
                    )
                    output_path = self.tmpdir / f"cleaned_{tag}.csv"
                    self.assertFalse(output_path.exists())
                    before_names = self.workspace_names()

                    result = self.run_cleaner(
                        input_path, output_path, delimiter=value
                    )

                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stdout, b"")
                    stderr_text = result.stderr.decode(
                        "utf-8", errors="replace"
                    )
                    # The diagnostic names the option and whether the
                    # value was missing or an illegal choice.
                    self.assertIn("--delimiter", stderr_text)
                    self.assertIn(reason, stderr_text)
                    if echoed is not None:
                        self.assertIn(echoed, stderr_text)
                    self.assertNotIn("Traceback", stderr_text)
                    self.assertFalse(output_path.exists())
                    # No output file or any other new file appears.
                    self.assertEqual(self.workspace_names(), before_names)
                    self.assertEqual(
                        input_path.read_bytes(), original_bytes
                    )

    def test_omitted_delimiter_keeps_default_comma_entry_point(self):
        # Control: without --delimiter a comma-separated file is read
        # and exported exactly as before the semicolon feature existed.
        comma_rows = [
            ["name", "note"],
            [" Alice ", "x,y"],
            ["   ", "ok"],
            ["Bob", "z"],
        ]
        expected_rows = [
            ["name", "note"],
            ["Alice", "x,y"],
            ["", "ok"],
            ["Bob", "z"],
        ]
        input_path, original_bytes = self.write_input(
            comma_rows, bom=False, tag="comma_default",
            field_delimiter=",",
        )
        output_path = self.tmpdir / "cleaned_comma_default.csv"

        result = self.run_cleaner(
            input_path, output_path, include_changes=True
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(
            json.loads(result.stdout.decode("utf-8")),
            {
                "rows": 3,
                "changed_cells": 2,
                "changes": [
                    {"record": 2, "column": "name",
                     "before": " Alice ", "after": "Alice"},
                    {"record": 3, "column": "name",
                     "before": "   ", "after": ""},
                ],
            },
        )
        self.assertTrue(output_path.exists())
        self.assertFalse(
            output_path.read_bytes().startswith(codecs.BOM_UTF8)
        )
        # The export parses under the comma dialect with the comma in
        # the note preserved.
        self.assertEqual(
            self.read_output_records(output_path, field_delimiter=","),
            expected_rows,
        )
        self.assertEqual(input_path.read_bytes(), original_bytes)


class TabDelimiterCliTests(unittest.TestCase):
    """Regression coverage for the explicit --delimiter tab switch.

    Every test goes through the documented public CLI against small
    UTF-8 CSV files in a private temporary directory: no external files
    or network. Results are judged on parsed CSV fields and the parsed
    JSON object, so equivalent quoting styles, record separators and
    JSON key order are irrelevant. The tab delimiter must be used to
    read the input, clean the named column and write the export.
    """

    # Acceptance sample serialized with real tab field separators. The
    # first note embeds a literal tab, a double quote and a quoted real
    # newline, so it can only round-trip when the same tab delimiter is
    # used for reading and writing and the quote handling stays intact.
    SAMPLE_ROWS = [
        ["name", "note"],
        [" Alice ", 'x\ty"z\nnext'],
        ["Bob", "ok"],
        ["   ", "z"],                 # three ASCII spaces trim to empty
        ["", "end"],                  # already empty: not a change
    ]
    EXPECTED_ROWS = [
        ["name", "note"],
        ["Alice", 'x\ty"z\nnext'],
        ["Bob", "ok"],
        ["", "z"],
        ["", "end"],
    ]
    EXPECTED_SUMMARY = {
        "rows": 4,
        "changed_cells": 2,
        "changes": [
            {"record": 2, "column": "name",
             "before": " Alice ", "after": "Alice"},
            {"record": 4, "column": "name",
             "before": "   ", "after": ""},
        ],
    }
    # Failure sample: the third data record holds only the name field.
    # The first note keeps its quoted real newline, so the short record
    # is CSV record 4 even though it sits on a later physical line.
    SHORT_RECORD_ROWS = [
        ["name", "note"],
        [" Alice ", 'x\ty"z\nnext'],
        ["Bob", "ok"],
        ["   "],
        ["", "end"],
    ]

    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.tmpdir = Path(self._tempdir.name)

    def write_input(self, rows, *, bom, tag):
        """Serialize rows with real tab field separators, as UTF-8 bytes."""
        buffer = io.StringIO()
        csv.writer(buffer, delimiter="\t").writerows(rows)
        encoding = "utf-8-sig" if bom else "utf-8"
        data = buffer.getvalue().encode(encoding)
        path = self.tmpdir / f"input_{tag}.csv"
        path.write_bytes(data)
        return path, data

    def run_cleaner(self, input_path, output_path, *,
                    dry_run=False, include_changes=False):
        argv = [
            sys.executable, str(SCRIPT_PATH),
            "--input", str(input_path),
            "--output", str(output_path),
            "--column", "name",
            "--rule", "trim",
            "--delimiter", "tab",
        ]
        if include_changes:
            argv.append("--include-changes")
        if dry_run:
            argv.append("--dry-run")
        return subprocess.run(
            argv, cwd=str(self.tmpdir), capture_output=True
        )

    def read_output_records(self, path):
        # Plain utf-8 (not utf-8-sig) so a stray BOM would surface as
        # content.
        with open(path, "r", encoding="utf-8", newline="") as outfile:
            return list(csv.reader(outfile, delimiter="\t"))

    def workspace_names(self):
        return sorted(p.name for p in self.tmpdir.iterdir())

    def test_tab_used_for_read_clean_and_export_with_and_without_bom(self):
        for bom in (False, True):
            with self.subTest(bom=bom):
                tag = "tab_bom" if bom else "tab_nobom"
                input_path, original_bytes = self.write_input(
                    self.SAMPLE_ROWS, bom=bom, tag=tag
                )
                output_path = self.tmpdir / f"cleaned_{tag}.csv"
                self.assertFalse(output_path.exists())

                result = self.run_cleaner(
                    input_path, output_path, include_changes=True
                )

                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, b"")
                # The whole stdout must parse as one JSON object and
                # nothing else; json.loads rejects trailing junk.
                summary = json.loads(result.stdout.decode("utf-8"))
                self.assertEqual(summary, self.EXPECTED_SUMMARY)

                self.assertTrue(output_path.exists())
                raw_output = output_path.read_bytes()
                # The export is BOM-free UTF-8 even when the input had
                # a BOM.
                self.assertFalse(raw_output.startswith(codecs.BOM_UTF8))
                # Read back with the tab dialect: the header, record
                # order and every note value survive, including the
                # embedded tab, double quote and real newline.
                self.assertEqual(
                    self.read_output_records(output_path),
                    self.EXPECTED_ROWS,
                )
                # The same bytes parsed as a comma CSV collapse to one
                # field per record, proving the export really uses tabs
                # rather than the comma default.
                with open(
                    output_path, "r", encoding="utf-8", newline=""
                ) as outfile:
                    comma_rows = list(csv.reader(outfile))
                self.assertTrue(
                    all(len(row) == 1 for row in comma_rows), comma_rows
                )

                # Without --include-changes the summary keeps its
                # two-key shape: no changes field at all.
                plain_path = self.tmpdir / f"cleaned_plain_{tag}.csv"
                plain = self.run_cleaner(input_path, plain_path)
                self.assertEqual(plain.returncode, 0)
                self.assertEqual(plain.stderr, b"")
                self.assertEqual(
                    json.loads(plain.stdout.decode("utf-8")),
                    {"rows": 4, "changed_cells": 2},
                )
                self.assertEqual(
                    self.read_output_records(plain_path),
                    self.EXPECTED_ROWS,
                )

                # The input file is opened read-only: exact bytes remain.
                self.assertEqual(input_path.read_bytes(), original_bytes)

    def test_tab_dry_run_matches_export_and_creates_nothing(self):
        for bom in (False, True):
            with self.subTest(bom=bom):
                tag = "tab_dry_bom" if bom else "tab_dry_nobom"
                input_path, original_bytes = self.write_input(
                    self.SAMPLE_ROWS, bom=bom, tag=tag
                )
                # Reference: a real export of the same input.
                export_path = self.tmpdir / f"export_{tag}.csv"
                export_result = self.run_cleaner(
                    input_path, export_path, include_changes=True
                )
                self.assertEqual(export_result.returncode, 0)
                reference_summary = json.loads(
                    export_result.stdout.decode("utf-8")
                )

                # The preview output sits below a parent directory that
                # does not exist.
                missing_dir = self.tmpdir / f"nodir_{tag}"
                preview_path = missing_dir / "cleaned.csv"
                self.assertFalse(missing_dir.exists())
                self.assertFalse(preview_path.exists())
                # Snapshot after the reference export: the preview must
                # not add even a directory or stray file on top of it.
                before_names = self.workspace_names()

                result = self.run_cleaner(
                    input_path, preview_path,
                    dry_run=True, include_changes=True,
                )

                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, b"")
                # Same JSON content as the real export, compared by
                # parsed content rather than key order or spacing.
                self.assertEqual(
                    json.loads(result.stdout.decode("utf-8")),
                    reference_summary,
                )
                # Neither the file nor its missing parent is created,
                # and nothing else appears in the workspace.
                self.assertFalse(preview_path.exists())
                self.assertFalse(missing_dir.exists())
                self.assertEqual(self.workspace_names(), before_names)
                self.assertEqual(input_path.read_bytes(), original_bytes)

    def test_short_record_fails_in_export_and_preview(self):
        input_path, original_bytes = self.write_input(
            self.SHORT_RECORD_ROWS, bom=False, tag="tab_short"
        )
        for dry_run in (False, True):
            with self.subTest(dry_run=dry_run):
                tag = "tab_short_dry" if dry_run else "tab_short"
                output_path = self.tmpdir / f"cleaned_{tag}.csv"
                self.assertFalse(output_path.exists())
                before_names = self.workspace_names()

                result = self.run_cleaner(
                    input_path, output_path, dry_run=dry_run,
                    include_changes=True,
                )

                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, b"")
                stderr_text = result.stderr.decode("utf-8")
                # The quoted newline in the first note must not advance
                # the record count: the short record is record 4.
                self.assertEqual(
                    stderr_text,
                    "error: record 4 has 1 field(s), expected 2\n",
                )
                self.assertNotIn("Traceback", stderr_text)
                # Neither mode leaves an output file or any other new
                # file behind, and the input bytes stay untouched.
                self.assertFalse(output_path.exists())
                self.assertEqual(self.workspace_names(), before_names)
                self.assertEqual(input_path.read_bytes(), original_bytes)


class OutputDelimiterCliTests(unittest.TestCase):
    """Regression coverage for the independent --output-delimiter switch.

    Every test goes through the documented public CLI against small
    UTF-8 CSV files in a private temporary directory: no external files
    or network. Results are judged on parsed CSV fields and the parsed
    JSON object, so equivalent quoting styles, record separators and
    JSON key order are irrelevant. The input is always read with the
    --delimiter choice (semicolon here); --output-delimiter overrides
    only the export format, and omitting it keeps the export on the
    input delimiter. A delimiter conversion is a pure format change and
    never counts as a changed cell.
    """

    # Acceptance sample serialized with semicolon field separators. The
    # first note embeds a semicolon, a comma, a double quote and a
    # quoted real newline, so it can only round-trip when each side
    # uses its own delimiter and the quote handling stays intact.
    SAMPLE_ROWS = [
        ["name", "note"],
        [" Alice ", 'x;y,z"q\nnext'],
        ["Bob", "ok"],
        ["   ", "end"],               # three ASCII spaces trim to empty
    ]
    EXPECTED_ROWS = [
        ["name", "note"],
        ["Alice", 'x;y,z"q\nnext'],
        ["Bob", "ok"],
        ["", "end"],
    ]
    EXPECTED_SUMMARY = {
        "rows": 3,
        "changed_cells": 2,
        "changes": [
            {"record": 2, "column": "name",
             "before": " Alice ", "after": "Alice"},
            {"record": 4, "column": "name",
             "before": "   ", "after": ""},
        ],
    }
    HEADER_ONLY_ROWS = [["name", "note"]]

    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.tmpdir = Path(self._tempdir.name)

    def write_input(self, rows, *, bom, tag):
        """Serialize rows with semicolon field separators, as UTF-8 bytes."""
        buffer = io.StringIO()
        csv.writer(buffer, delimiter=";").writerows(rows)
        encoding = "utf-8-sig" if bom else "utf-8"
        data = buffer.getvalue().encode(encoding)
        path = self.tmpdir / f"input_{tag}.csv"
        path.write_bytes(data)
        return path, data

    def run_cleaner(self, input_path, output_path, *,
                    output_delimiter="OMITTED",
                    dry_run=False, include_changes=False):
        # output_delimiter="OMITTED" means --output-delimiter is not
        # passed at all (the export reuses the input delimiter); None
        # means the bare flag with no following value.
        argv = [
            sys.executable, str(SCRIPT_PATH),
            "--input", str(input_path),
            "--output", str(output_path),
            "--column", "name",
            "--rule", "trim",
            "--delimiter", "semicolon",
        ]
        if output_delimiter != "OMITTED":
            argv.append("--output-delimiter")
            if output_delimiter is not None:
                argv.append(output_delimiter)
        if include_changes:
            argv.append("--include-changes")
        if dry_run:
            argv.append("--dry-run")
        return subprocess.run(
            argv, cwd=str(self.tmpdir), capture_output=True
        )

    def read_output_records(self, path, field_delimiter):
        # Plain utf-8 (not utf-8-sig) so a stray BOM would surface as
        # content.
        with open(path, "r", encoding="utf-8", newline="") as outfile:
            return list(csv.reader(outfile, delimiter=field_delimiter))

    def workspace_names(self):
        return sorted(p.name for p in self.tmpdir.iterdir())

    def test_comma_export_with_and_without_bom(self):
        for bom in (False, True):
            with self.subTest(bom=bom):
                tag = "outcomma_bom" if bom else "outcomma_nobom"
                input_path, original_bytes = self.write_input(
                    self.SAMPLE_ROWS, bom=bom, tag=tag
                )
                output_path = self.tmpdir / f"cleaned_{tag}.csv"
                self.assertFalse(output_path.exists())

                result = self.run_cleaner(
                    input_path, output_path,
                    output_delimiter="comma", include_changes=True,
                )

                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, b"")
                # The whole stdout must parse as one JSON object and
                # nothing else; json.loads rejects trailing junk. The
                # delimiter conversion itself is not a change, so only
                # the two trimmed cells are listed.
                summary = json.loads(result.stdout.decode("utf-8"))
                self.assertEqual(summary, self.EXPECTED_SUMMARY)

                self.assertTrue(output_path.exists())
                raw_output = output_path.read_bytes()
                # The export is BOM-free UTF-8 even when the input had
                # a BOM.
                self.assertFalse(raw_output.startswith(codecs.BOM_UTF8))
                # Read back with the comma dialect: the header, record
                # order and every note value survive, including the
                # embedded semicolon, comma, double quote and real
                # newline.
                self.assertEqual(
                    self.read_output_records(output_path, ","),
                    self.EXPECTED_ROWS,
                )
                # Parsed as a semicolon CSV the header collapses to one
                # field, proving the export really uses commas rather
                # than the semicolon the input was read with.
                semicolon_rows = self.read_output_records(output_path, ";")
                self.assertEqual(semicolon_rows[0], ["name,note"])

                # Without --include-changes the summary keeps its
                # two-key shape: no changes field at all.
                plain_path = self.tmpdir / f"cleaned_plain_{tag}.csv"
                plain = self.run_cleaner(
                    input_path, plain_path, output_delimiter="comma"
                )
                self.assertEqual(plain.returncode, 0)
                self.assertEqual(plain.stderr, b"")
                self.assertEqual(
                    json.loads(plain.stdout.decode("utf-8")),
                    {"rows": 3, "changed_cells": 2},
                )
                self.assertEqual(
                    self.read_output_records(plain_path, ","),
                    self.EXPECTED_ROWS,
                )

                # The input file is opened read-only: exact bytes remain.
                self.assertEqual(input_path.read_bytes(), original_bytes)

    def test_tab_export_reads_back_with_tab_dialect(self):
        input_path, original_bytes = self.write_input(
            self.SAMPLE_ROWS, bom=False, tag="outtab"
        )
        output_path = self.tmpdir / "cleaned_outtab.csv"
        self.assertFalse(output_path.exists())

        result = self.run_cleaner(
            input_path, output_path,
            output_delimiter="tab", include_changes=True,
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(
            json.loads(result.stdout.decode("utf-8")),
            self.EXPECTED_SUMMARY,
        )
        self.assertTrue(output_path.exists())
        raw_output = output_path.read_bytes()
        self.assertFalse(raw_output.startswith(codecs.BOM_UTF8))
        # Read back with the tab dialect: the header, record order and
        # every note value survive the semicolon-to-tab conversion.
        self.assertEqual(
            self.read_output_records(output_path, "\t"),
            self.EXPECTED_ROWS,
        )
        # Parsed as a semicolon CSV the header collapses to one field,
        # proving the export really uses tabs.
        semicolon_rows = self.read_output_records(output_path, ";")
        self.assertEqual(semicolon_rows[0], ["name\tnote"])
        self.assertEqual(input_path.read_bytes(), original_bytes)

    def test_omitted_output_delimiter_reuses_input_delimiter(self):
        # Without --output-delimiter the export is written with the
        # same semicolon delimiter the input was read with.
        input_path, original_bytes = self.write_input(
            self.SAMPLE_ROWS, bom=False, tag="outdefault"
        )
        output_path = self.tmpdir / "cleaned_outdefault.csv"
        self.assertFalse(output_path.exists())

        result = self.run_cleaner(
            input_path, output_path, include_changes=True
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(
            json.loads(result.stdout.decode("utf-8")),
            self.EXPECTED_SUMMARY,
        )
        self.assertTrue(output_path.exists())
        self.assertFalse(
            output_path.read_bytes().startswith(codecs.BOM_UTF8)
        )
        self.assertEqual(
            self.read_output_records(output_path, ";"),
            self.EXPECTED_ROWS,
        )
        # Parsed as a comma CSV the header collapses to one field,
        # proving the export stayed on the semicolon input delimiter.
        comma_rows = self.read_output_records(output_path, ",")
        self.assertEqual(comma_rows[0], ["name;note"])
        self.assertEqual(input_path.read_bytes(), original_bytes)

    def test_dry_run_matches_export_and_creates_nothing(self):
        for bom in (False, True):
            with self.subTest(bom=bom):
                tag = "outdry_bom" if bom else "outdry_nobom"
                input_path, original_bytes = self.write_input(
                    self.SAMPLE_ROWS, bom=bom, tag=tag
                )
                # Reference: a real comma export of the same input.
                export_path = self.tmpdir / f"export_{tag}.csv"
                export_result = self.run_cleaner(
                    input_path, export_path,
                    output_delimiter="comma", include_changes=True,
                )
                self.assertEqual(export_result.returncode, 0)
                reference_summary = json.loads(
                    export_result.stdout.decode("utf-8")
                )

                # The preview output sits below a parent directory that
                # does not exist.
                missing_dir = self.tmpdir / f"nodir_{tag}"
                preview_path = missing_dir / "cleaned.csv"
                self.assertFalse(missing_dir.exists())
                self.assertFalse(preview_path.exists())
                # Snapshot after the reference export: the preview must
                # not add even a directory or stray file on top of it.
                before_names = self.workspace_names()

                result = self.run_cleaner(
                    input_path, preview_path,
                    output_delimiter="comma",
                    dry_run=True, include_changes=True,
                )

                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, b"")
                # Same JSON content as the real export, compared by
                # parsed content rather than key order or spacing.
                self.assertEqual(
                    json.loads(result.stdout.decode("utf-8")),
                    reference_summary,
                )
                # Neither the file nor its missing parent is created,
                # and nothing else appears in the workspace.
                self.assertFalse(preview_path.exists())
                self.assertFalse(missing_dir.exists())
                self.assertEqual(self.workspace_names(), before_names)
                self.assertEqual(input_path.read_bytes(), original_bytes)

    def test_invalid_output_delimiter_values_rejected(self):
        # None: the bare --output-delimiter flag with no following
        # value; "": an explicit empty string; "Comma": the lowercase
        # choice names are case-sensitive. argparse must reject each
        # one (exit 2) before any file is touched, on both the data
        # sample and a header-only file.
        cases = [
            (None, "expected one argument", None),
            ("", "invalid choice", "''"),
            ("Comma", "invalid choice", "Comma"),
        ]
        for sample_name, rows in (
            ("data", self.SAMPLE_ROWS),
            ("header_only", self.HEADER_ONLY_ROWS),
        ):
            for value, reason, echoed in cases:
                with self.subTest(sample=sample_name, value=value):
                    tag = "outdelim_%s_%s" % (
                        sample_name,
                        {None: "missing", "": "empty",
                         "Comma": "capitalized"}[value],
                    )
                    input_path, original_bytes = self.write_input(
                        rows, bom=False, tag=tag
                    )
                    output_path = self.tmpdir / f"cleaned_{tag}.csv"
                    self.assertFalse(output_path.exists())
                    before_names = self.workspace_names()

                    result = self.run_cleaner(
                        input_path, output_path, output_delimiter=value
                    )

                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stdout, b"")
                    stderr_text = result.stderr.decode(
                        "utf-8", errors="replace"
                    )
                    # The diagnostic names the option and whether the
                    # value was missing or an illegal choice.
                    self.assertIn("--output-delimiter", stderr_text)
                    self.assertIn(reason, stderr_text)
                    if echoed is not None:
                        self.assertIn(echoed, stderr_text)
                    self.assertNotIn("Traceback", stderr_text)
                    self.assertFalse(output_path.exists())
                    # No output file or any other new file appears.
                    self.assertEqual(self.workspace_names(), before_names)
                    self.assertEqual(
                        input_path.read_bytes(), original_bytes
                    )


class NullReplacementDelimiterConversionTests(unittest.TestCase):
    """normalize-null text fidelity on a semicolon-to-comma conversion.

    These tests pin only this one combination of features:
    normalize-null with a custom marker and a replacement text packed
    with every quoting hazard, read with --delimiter semicolon and
    exported with --output-delimiter comma. Every test goes through the
    documented public CLI against small UTF-8 CSV files in a private
    temporary directory (created and removed with the standard
    tempfile machinery): no external files or network. Results are
    judged on parsed CSV fields and the parsed JSON object, so
    equivalent quoting styles, record separators and JSON key order are
    irrelevant.
    """

    # The three parsed data rows:
    #   (" NULL ", "a;b")
    #   ("待补",   "line one\nline two")
    #   (" Bob ",  "ok")
    # The second note embeds a real newline, which is quoted in the
    # file and must not advance the CSV record number.
    SAMPLE_ROWS = [
        ["name", "note"],
        [" NULL ", "a;b"],
        ["待补", "line one\nline two"],
        [" Bob ", "ok"],
    ]
    # Failure sample: the third data record is a single field, which
    # must be reported as record 4 (the header is record 1, and the
    # quoted newline inside the previous note does not add a record).
    SHORT_RECORD_ROWS = [
        ["name", "note"],
        [" NULL ", "a;b"],
        ["待补", "line one\nline two"],
        ["onlyone"],
    ]

    MARKER = "待补"
    # One space at each end; inside sit a comma, a semicolon, double
    # quotes and one real newline. Every character must survive into
    # both the JSON summary and the comma export.
    REPLACEMENT = ' 未知,待补;"待定"\n下一行 '

    EXPECTED_ROWS = [
        ["name", "note"],
        [REPLACEMENT, "a;b"],
        [REPLACEMENT, "line one\nline two"],
        [" Bob ", "ok"],
    ]
    EXPECTED_SUMMARY = {
        "rows": 3,
        "changed_cells": 2,
        "changes": [
            {"record": 2, "column": "name",
             "before": " NULL ", "after": REPLACEMENT},
            {"record": 3, "column": "name",
             "before": MARKER, "after": REPLACEMENT},
        ],
    }

    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.tmpdir = Path(self._tempdir.name)

    def write_input(self, rows, *, bom, tag):
        """Serialize rows with semicolon separators, as UTF-8 bytes."""
        buffer = io.StringIO()
        csv.writer(buffer, delimiter=";").writerows(rows)
        encoding = "utf-8-sig" if bom else "utf-8"
        data = buffer.getvalue().encode(encoding)
        path = self.tmpdir / f"input_{tag}.csv"
        path.write_bytes(data)
        return path, data

    def run_cleaner(self, input_path, output_path, *,
                    dry_run=False):
        argv = [
            sys.executable, str(SCRIPT_PATH),
            "--input", str(input_path),
            "--output", str(output_path),
            "--column", "name",
            "--rule", "normalize-null",
            "--delimiter", "semicolon",
            "--output-delimiter", "comma",
            "--null-marker", self.MARKER,
            "--null-replacement", self.REPLACEMENT,
            "--include-changes",
        ]
        if dry_run:
            argv.append("--dry-run")
        return subprocess.run(
            argv, cwd=str(self.tmpdir), capture_output=True
        )

    def read_output_records(self, path):
        # Plain utf-8 (not utf-8-sig) so a stray BOM would surface as
        # content; the export is parsed with the comma dialect.
        with open(path, "r", encoding="utf-8", newline="") as outfile:
            return list(csv.reader(outfile, delimiter=","))

    def workspace_names(self):
        return sorted(p.name for p in self.tmpdir.iterdir())

    def test_preview_and_export_match_with_and_without_bom(self):
        for bom in (False, True):
            with self.subTest(bom=bom):
                tag = "nullconv_bom" if bom else "nullconv_nobom"
                input_path, original_bytes = self.write_input(
                    self.SAMPLE_ROWS, bom=bom, tag=tag
                )

                # Preview into a path below a parent directory that
                # does not exist.
                missing_dir = self.tmpdir / f"nodir_{tag}"
                preview_path = missing_dir / "preview.csv"
                self.assertFalse(missing_dir.exists())
                self.assertFalse(preview_path.exists())
                before_names = self.workspace_names()

                preview = self.run_cleaner(
                    input_path, preview_path, dry_run=True
                )

                self.assertEqual(preview.returncode, 0)
                self.assertEqual(preview.stderr, b"")
                # The whole stdout is one JSON object and nothing else.
                preview_summary = json.loads(
                    preview.stdout.decode("utf-8")
                )
                self.assertEqual(preview_summary, self.EXPECTED_SUMMARY)
                # The preview creates neither the file nor its missing
                # parent, nor anything else in the workspace.
                self.assertFalse(preview_path.exists())
                self.assertFalse(missing_dir.exists())
                self.assertEqual(self.workspace_names(), before_names)

                # Real export into the existing temporary directory as
                # a fresh filename.
                output_path = self.tmpdir / f"cleaned_{tag}.csv"
                self.assertFalse(output_path.exists())

                result = self.run_cleaner(input_path, output_path)

                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, b"")
                export_summary = json.loads(
                    result.stdout.decode("utf-8")
                )
                # Parsed JSON content is identical between preview and
                # export (no reliance on key order or spacing).
                self.assertEqual(export_summary, preview_summary)
                self.assertEqual(export_summary, self.EXPECTED_SUMMARY)

                # The export is BOM-free UTF-8 even when the input had
                # a BOM.
                raw_output = output_path.read_bytes()
                raw_output.decode("utf-8")
                self.assertFalse(raw_output.startswith(codecs.BOM_UTF8))

                # Parsed with commas the export still has exactly two
                # fields per record: the replacement's own commas,
                # semicolon, quotes and real newline must all be
                # carried inside the quoted name field.
                output_rows = self.read_output_records(output_path)
                self.assertTrue(
                    all(len(row) == 2 for row in output_rows),
                    output_rows,
                )
                self.assertEqual(output_rows, self.EXPECTED_ROWS)
                # Header and record order unchanged...
                self.assertEqual(
                    [row[0] for row in output_rows],
                    [row[0] for row in self.EXPECTED_ROWS],
                )
                # ...and the note column is byte-for-byte the parsed
                # input notes, including the quoted real newline.
                self.assertEqual(
                    [row[1] for row in output_rows],
                    [row[1] for row in self.SAMPLE_ROWS],
                )
                # The untouched third name keeps both surrounding
                # spaces.
                self.assertEqual(output_rows[3][0], " Bob ")
                self.assertTrue(
                    output_rows[3][0].startswith(" ")
                    and output_rows[3][0].endswith(" ")
                )

                # The input file is opened read-only: exact bytes
                # remain, BOM and all.
                self.assertEqual(
                    input_path.read_bytes(), original_bytes
                )

    def test_short_record_fails_in_preview_and_export(self):
        # The short-record variant is exercised without a BOM; its
        # quoted-note newline must not inflate the record number.
        input_path, original_bytes = self.write_input(
            self.SHORT_RECORD_ROWS, bom=False, tag="nullconv_short"
        )
        missing_dir = self.tmpdir / "nodir_nullconv_short"
        for dry_run in (False, True):
            with self.subTest(dry_run=dry_run):
                if dry_run:
                    output_path = missing_dir / "preview.csv"
                    self.assertFalse(missing_dir.exists())
                else:
                    output_path = (
                        self.tmpdir / "cleaned_nullconv_short.csv"
                    )
                self.assertFalse(output_path.exists())
                before_names = self.workspace_names()

                result = self.run_cleaner(
                    input_path, output_path, dry_run=dry_run
                )

                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, b"")
                self.assertEqual(
                    result.stderr.decode("utf-8"),
                    "error: record 4 has 1 field(s), expected 2\n",
                )
                self.assertNotIn(
                    "Traceback", result.stderr.decode("utf-8")
                )
                self.assertFalse(output_path.exists())
                # No output file, no missing parent, no stray file.
                self.assertFalse(missing_dir.exists())
                self.assertEqual(self.workspace_names(), before_names)
                self.assertEqual(
                    input_path.read_bytes(), original_bytes
                )


class IncludeNullMatchesCliTests(unittest.TestCase):
    """Coverage for the --include-null-matches switch of normalize-null.

    The hit detail lists every cell the null rule matches, whether or
    not the replacement actually changes the cell text; it is
    independent of --include-changes. Every test goes through the
    documented public CLI against small UTF-8 CSV files in private
    temporary directories, judged on parsed CSV fields and the parsed
    JSON object so CSV quoting style and JSON key order are irrelevant,
    using only the standard library.
    """

    # state,note header plus five data records. The states parse as the
    # empty string, " NULL ", missing, N/A and NULLABLE; only the first
    # note carries a quoted real newline. The real newline is quoted
    # inside one field, so it must not advance the CSV record number
    # (the header is record 1): the five data rows are records 2-6.
    SAMPLE_ROWS = [
        ["state", "note"],
        ["", 'line one\nline two'],   # record 2: empty -> missing (changed)
        [" NULL ", "ok"],             # record 3: default marker (changed)
        ["missing", "ok"],            # record 4: custom marker, no change
        ["N/A", "ok"],                # record 5: default marker (changed)
        ["NULLABLE", "ok"],           # record 6: near miss, verbatim
    ]
    MARKER = "MISSING"
    REPLACEMENT = "missing"

    # Every cell above except NULLABLE matches the null rule; matches
    # keep the parsed original text (surrounding whitespace included).
    EXPECTED_NULL_MATCHES = [
        {"record": 2, "column": "state", "before": ""},
        {"record": 3, "column": "state", "before": " NULL "},
        {"record": 4, "column": "state", "before": "missing"},
        {"record": 5, "column": "state", "before": "N/A"},
    ]
    # Record 4 already spells the replacement, so it matches without
    # being a change; only records 2, 3 and 5 change.
    EXPECTED_CHANGES = [
        {"record": 2, "column": "state", "before": "",
         "after": REPLACEMENT},
        {"record": 3, "column": "state", "before": " NULL ",
         "after": REPLACEMENT},
        {"record": 5, "column": "state", "before": "N/A",
         "after": REPLACEMENT},
    ]
    EXPECTED_STATES = [
        REPLACEMENT, REPLACEMENT, REPLACEMENT, REPLACEMENT, "NULLABLE",
    ]

    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.tmpdir = Path(self._tempdir.name)

    def write_input(self, rows, *, tag, bom=False):
        data = encode_csv(rows, bom=bom)
        path = self.tmpdir / f"input_{tag}.csv"
        path.write_bytes(data)
        return path, data

    def run_cleaner(self, input_path, output_path, *, column="state",
                    rule="normalize-null", include_null_matches=False,
                    include_changes=False, dry_run=False,
                    markers=(), replacement=None):
        argv = [
            sys.executable,
            str(SCRIPT_PATH),
            "--input", str(input_path),
            "--output", str(output_path),
            "--column", column,
            "--rule", rule,
        ]
        for marker in markers:
            argv += ["--null-marker", marker]
        if replacement is not None:
            argv += ["--null-replacement", replacement]
        if include_null_matches:
            argv.append("--include-null-matches")
        if include_changes:
            argv.append("--include-changes")
        if dry_run:
            argv.append("--dry-run")
        return subprocess.run(
            argv, cwd=str(self.tmpdir), capture_output=True
        )

    def read_output_records(self, path):
        # Plain utf-8 (not utf-8-sig) so a stray BOM would surface as content.
        with open(path, "r", encoding="utf-8", newline="") as outfile:
            return list(csv.reader(outfile))

    def test_preview_and_export_report_identical_hit_and_change_detail(self):
        # Acceptance run: custom marker MISSING, replacement missing,
        # both detail switches. The preview points below a parent
        # directory that does not exist; the real export points at a
        # fresh file. Both must exit 0 with empty stderr and print the
        # same single parsed JSON object, and neither run may alter the
        # input bytes.
        input_path, original_bytes = self.write_input(
            self.SAMPLE_ROWS, tag="null_matches"
        )
        missing_dir = self.tmpdir / "nodir"
        preview_path = missing_dir / "preview.csv"
        export_path = self.tmpdir / "exported.csv"
        self.assertFalse(missing_dir.exists())
        self.assertFalse(preview_path.exists())
        self.assertFalse(export_path.exists())

        preview = self.run_cleaner(
            input_path, preview_path,
            markers=[self.MARKER], replacement=self.REPLACEMENT,
            include_null_matches=True, include_changes=True, dry_run=True,
        )

        self.assertEqual(preview.returncode, 0)
        self.assertEqual(preview.stderr, b"")
        preview_summary = json.loads(preview.stdout.decode("utf-8"))
        self.assertEqual(
            preview_summary,
            {
                "rows": 5,
                "changed_cells": 3,
                "null_matches": self.EXPECTED_NULL_MATCHES,
                "changes": self.EXPECTED_CHANGES,
            },
        )
        # null_matches entries carry only record/column/before; changes
        # entries additionally carry after.
        self.assertEqual(
            [set(entry) for entry in preview_summary["null_matches"]],
            [{"record", "column", "before"}] * 4,
        )
        self.assertEqual(
            [set(entry) for entry in preview_summary["changes"]],
            [{"record", "column", "before", "after"}] * 3,
        )
        # The preview creates neither the file nor its missing parent.
        self.assertFalse(preview_path.exists())
        self.assertFalse(missing_dir.exists())
        self.assertEqual(input_path.read_bytes(), original_bytes)

        result = self.run_cleaner(
            input_path, export_path,
            markers=[self.MARKER], replacement=self.REPLACEMENT,
            include_null_matches=True, include_changes=True,
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        # Same JSON content (parsed comparison, key order irrelevant).
        self.assertEqual(
            json.loads(result.stdout.decode("utf-8")), preview_summary
        )

        raw_output = export_path.read_bytes()
        self.assertFalse(raw_output.startswith(codecs.BOM_UTF8))
        output_rows = self.read_output_records(export_path)
        # Header, record order and the untouched note column (including
        # the quoted real newline in the first note) are preserved.
        self.assertEqual(output_rows[0], ["state", "note"])
        self.assertEqual(len(output_rows), 6)
        self.assertEqual(
            [row[0] for row in output_rows[1:]], self.EXPECTED_STATES
        )
        self.assertEqual(
            [row[1] for row in output_rows],
            [row[1] for row in self.SAMPLE_ROWS],
        )
        self.assertEqual(input_path.read_bytes(), original_bytes)

    def test_switch_combination_matrix_shapes_and_results(self):
        # The two detail switches are independent. Omitting the hit
        # detail leaves null_matches out (with and without changes);
        # enabling only the hit detail leaves changes out; counts and
        # the exported CSV are identical in every combination.
        expected_counts = {"rows": 5, "changed_cells": 3}
        exports = {}
        for include_null_matches in (False, True):
            for include_changes in (False, True):
                with self.subTest(
                    include_null_matches=include_null_matches,
                    include_changes=include_changes,
                ):
                    tag = (
                        f"matrix_"
                        f"{'nm' if include_null_matches else 'no'}_"
                        f"{'ch' if include_changes else 'no'}"
                    )
                    input_path, original_bytes = self.write_input(
                        self.SAMPLE_ROWS, tag=tag
                    )
                    output_path = self.tmpdir / f"{tag}.csv"

                    result = self.run_cleaner(
                        input_path, output_path,
                        markers=[self.MARKER],
                        replacement=self.REPLACEMENT,
                        include_null_matches=include_null_matches,
                        include_changes=include_changes,
                    )

                    self.assertEqual(result.returncode, 0)
                    self.assertEqual(result.stderr, b"")
                    summary = json.loads(result.stdout.decode("utf-8"))
                    expected = dict(expected_counts)
                    if include_null_matches:
                        expected["null_matches"] = \
                            self.EXPECTED_NULL_MATCHES
                    else:
                        self.assertNotIn("null_matches", summary)
                    if include_changes:
                        expected["changes"] = self.EXPECTED_CHANGES
                    else:
                        self.assertNotIn("changes", summary)
                    self.assertEqual(summary, expected)

                    output_rows = self.read_output_records(output_path)
                    self.assertEqual(
                        [row[0] for row in output_rows[1:]],
                        self.EXPECTED_STATES,
                    )
                    exports[(include_null_matches, include_changes)] = \
                        output_path.read_bytes()
                    self.assertEqual(
                        input_path.read_bytes(), original_bytes
                    )
        # The detail switches never affect the exported CSV.
        export_bytes = next(iter(exports.values()))
        self.assertTrue(all(data == export_bytes for data in exports.values()))

    def test_header_only_reports_zero_counts_and_empty_arrays(self):
        # With both detail switches a header-only file still exports
        # just the header: no rows, no matches, no changes.
        input_path, original_bytes = self.write_input(
            [["state", "note"]], tag="null_matches_header_only"
        )
        output_path = self.tmpdir / "header_only_export.csv"

        result = self.run_cleaner(
            input_path, output_path,
            markers=[self.MARKER], replacement=self.REPLACEMENT,
            include_null_matches=True, include_changes=True,
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(
            json.loads(result.stdout.decode("utf-8")),
            {
                "rows": 0,
                "changed_cells": 0,
                "null_matches": [],
                "changes": [],
            },
        )
        self.assertEqual(self.read_output_records(output_path),
                         [["state", "note"]])
        self.assertEqual(input_path.read_bytes(), original_bytes)

    def test_switch_with_trim_rejected_even_on_header_only_input(self):
        # --include-null-matches is only valid with normalize-null; the
        # rejection happens before the input is read, so a perfectly
        # valid header-only input must not make the pairing acceptable.
        input_path, original_bytes = self.write_input(
            [["state", "note"]], tag="null_matches_trim"
        )
        output_path = self.tmpdir / "trim_export.csv"
        self.assertFalse(output_path.exists())

        result = self.run_cleaner(
            input_path, output_path, rule="trim",
            include_null_matches=True, include_changes=True,
        )

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        stderr_text = result.stderr.decode("utf-8")
        self.assertIn(
            "--include-null-matches can only be used with "
            "--rule normalize-null",
            stderr_text,
        )
        self.assertNotIn("Traceback", stderr_text)
        self.assertFalse(output_path.exists())
        self.assertEqual(input_path.read_bytes(), original_bytes)


if __name__ == "__main__":
    unittest.main()

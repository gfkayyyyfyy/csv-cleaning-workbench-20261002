#!/usr/bin/env python3
"""Local CSV cleaner: apply one explicit rule to one column of a UTF-8 CSV.

Usage:
    python csv_cleaner.py --input input.csv --output cleaned.csv \
        --column name --rule trim

normalize-null additionally accepts repeatable custom null markers:

    python csv_cleaner.py --input input.csv --output cleaned.csv \
        --column name --rule normalize-null \
        --null-marker MISSING --null-marker 待补

normalize-date additionally accepts --date-order to choose how a slash
date with the year last is read:

    python csv_cleaner.py --input input.csv --output cleaned.csv \
        --column due_date --rule normalize-date --date-order mdy

    --date-order accepts only lowercase dmy and mdy; omitting it is the
    same as dmy (DD/MM/YYYY). Under mdy the year-last slash date is read
    as MM/DD/YYYY, with ambiguous fields settled by the chosen order and
    no guessing or fallback. YYYY-MM-DD and YYYY/MM/DD stay
    year-month-day under either order.

normalize-whitespace strips both ends and collapses every internal run
of whitespace (judged by str.isspace) to one ASCII space:

    python csv_cleaner.py --input input.csv --output cleaned.csv \
        --column name --rule normalize-whitespace

On success prints a single JSON object to stdout, e.g.
    {"rows": 3, "changed_cells": 2}
and exits 0. Any failure exits 2 with the reason on stderr and no output
file is created.

With --include-changes the same JSON object gains a "changes" array with
one {"record", "column", "before", "after"} entry per changed cell, in
record order; no separate detail file is written.

With --dry-run the input is fully read and validated and the same summary
JSON is printed, but no output file or directory is created. The output
path must still differ from the input and must not already exist; a
missing parent directory or unwritable location does not fail the
preview, so a successful dry run does not guarantee a real export would
succeed.
"""

import argparse
import csv
import json
import os
import re
import sys
from datetime import date
from functools import partial

NULL_MARKERS = frozenset({"null", "n/a"})

# [0-9] rather than \d so only ASCII digits are accepted.
DATE_ISO_RE = re.compile(r"^([0-9]{4})-([0-9]{2})-([0-9]{2})$")
# A slash date whose four-digit year is last. The two leading fields are
# day/month under dmy and month/day under mdy, never guessed.
DATE_SLASH_YEAR_RE = re.compile(r"^([0-9]{2})/([0-9]{2})/([0-9]{4})$")
DATE_YMD_SLASH_RE = re.compile(r"^([0-9]{4})/([0-9]{2})/([0-9]{2})$")

# Accepted --date-order values: how to read a NN/NN/YYYY slash date.
DATE_ORDERS = ("dmy", "mdy")
DEFAULT_DATE_ORDER = "dmy"


class InvalidDateError(ValueError):
    """Raised when a cell is not an accepted calendar date."""


def ascii_lower(text):
    """Lowercase ASCII A-Z only; all other characters stay untouched."""
    return "".join(
        chr(ord(ch) + 32) if "A" <= ch <= "Z" else ch for ch in text
    )


def normalize_null(value, extra_markers=frozenset()):
    """Normalize null markers to an empty string.

    After stripping both ends, the cell becomes empty when the result is
    empty or matches NULL / N/A (or any of the given extra markers)
    case-insensitively with respect to ASCII letters. Anything else is
    returned byte-for-byte, including its surrounding whitespace (e.g.
    "NULLABLE" is not a marker). Extra markers are compared after
    str.strip() themselves; duplicate markers collapse into one match but
    never inflate the change count.
    """
    stripped = value.strip()
    if not stripped:
        return ""
    lowered = ascii_lower(stripped)
    if lowered in NULL_MARKERS or lowered in extra_markers:
        return ""
    return value


def normalize_date(value, date_order=DEFAULT_DATE_ORDER):
    """Normalize an accepted date spelling to YYYY-MM-DD.

    After stripping both ends, an empty cell stays empty. Anything else
    must be exactly YYYY-MM-DD, YYYY/MM/DD or a slash date with the
    four-digit year last (NN/NN/YYYY), using ASCII digits, a four-digit
    year and two-digit month/day, and must be a real proleptic Gregorian
    calendar date in years 0001-9999; the result is always spelled
    YYYY-MM-DD.

    The year-last slash date is read by the explicit date_order only:
    "dmy" reads it as DD/MM/YYYY and "mdy" as MM/DD/YYYY. Ambiguous
    values follow that order with no guessing or fallback (under mdy
    13/02/2024 means month 13 and is invalid). YYYY-MM-DD and
    YYYY/MM/DD are always year-month-day under either order. Internal
    whitespace, unpadded numbers, time suffixes and null markers such
    as NULL or N/A are invalid and raise InvalidDateError.
    """
    stripped = value.strip()
    if not stripped:
        return ""
    match = DATE_ISO_RE.match(stripped)
    if match:
        year, month, day = (int(part) for part in match.groups())
    else:
        match = DATE_YMD_SLASH_RE.match(stripped)
        if match:
            year, month, day = (int(part) for part in match.groups())
        else:
            match = DATE_SLASH_YEAR_RE.match(stripped)
            if match:
                first, second, year = (int(part) for part in match.groups())
                if date_order == "mdy":
                    month, day = first, second
                else:
                    day, month = first, second
            else:
                raise InvalidDateError(f"invalid date: {value!r}")
    try:
        normalized = date(year, month, day)
    except ValueError:
        raise InvalidDateError(f"invalid date: {value!r}") from None
    return normalized.isoformat()


def normalize_whitespace(value):
    """Collapse whitespace to single ASCII spaces and strip both ends.

    Whitespace is judged by str.isspace (space, tab, carriage return,
    newline, ideographic space U+3000, ...): both ends are stripped and
    every internal run of whitespace becomes one ASCII space. An empty
    string stays empty and a whitespace-only string becomes empty. All
    other characters and their order are preserved, including the
    zero-width space U+200B, which str.isspace does not count as
    whitespace. NULL / N/A text and date text are only
    whitespace-normalized, never otherwise converted.
    """
    return " ".join(value.split())


RULES = {
    "trim": str.strip,
    "normalize-null": normalize_null,
    "normalize-date": normalize_date,
    "normalize-whitespace": normalize_whitespace,
}


def fail(message):
    print(f"error: {message}", file=sys.stderr)
    sys.exit(2)


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="csv_cleaner.py",
        description="Apply one explicit cleaning rule to one column of a "
                    "UTF-8 CSV file and write the result to a new file.",
    )
    parser.add_argument("--input", required=True,
                        help="path to the input CSV file (opened read-only)")
    parser.add_argument("--output", required=True,
                        help="path to the output CSV file (must not exist yet)")
    parser.add_argument("--column", required=True,
                        help="exact name of the single column to clean")
    parser.add_argument("--rule", required=True,
                        help="cleaning rule to apply (supported: "
                             + ", ".join(sorted(RULES)) + ")")
    parser.add_argument("--null-marker", action="append", default=[],
                        metavar="MARKER",
                        help="additional whole-value null marker for "
                             "normalize-null (may be repeated; the value "
                             "is stripped at both ends and compared "
                             "case-insensitively on ASCII letters only)")
    parser.add_argument("--date-order", choices=DATE_ORDERS, default=None,
                        metavar="ORDER",
                        help="how to read a slash date with the year last "
                             "for normalize-date: dmy (DD/MM/YYYY, the "
                             "default when omitted) or mdy (MM/DD/YYYY); "
                             "YYYY-MM-DD and YYYY/MM/DD stay year-month-day "
                             "under either order")
    parser.add_argument("--include-changes", action="store_true",
                        help="add a changes array to the success summary "
                             "with one {record, column, before, after} "
                             "entry per changed cell, in record order")
    parser.add_argument("--dry-run", action="store_true",
                        help="preview only: fully read and validate the "
                             "input and print the same summary JSON, but "
                             "create no output file or directory")
    return parser.parse_args(argv)


def read_records(path):
    """Read all CSV records, returning a list of (record_number, fields).

    Record numbers start at 1 for the header; quoted newlines inside a
    field do not advance the number.
    """
    records = []
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as infile:
            reader = csv.reader(infile, strict=True)
            try:
                for record_no, record in enumerate(reader, start=1):
                    records.append((record_no, record))
            except csv.Error as exc:
                fail(f"cannot parse CSV in {path!r}: {exc}")
            except UnicodeDecodeError as exc:
                fail(f"input file {path!r} is not valid UTF-8: {exc}")
    except OSError as exc:
        fail(f"cannot read input file {path!r}: {exc}")
    return records


def main(argv=None):
    args = parse_args(argv)

    rule = RULES.get(args.rule)
    if rule is None:
        fail(f"unsupported rule {args.rule!r} "
             f"(supported: {', '.join(sorted(RULES))})")

    # --null-marker is only meaningful for normalize-null, and every
    # marker must name a non-empty value after str.strip() (whitespace
    # around the marker is tolerated; whitespace-only markers are not).
    if args.null_marker and args.rule != "normalize-null":
        fail("--null-marker can only be used with --rule normalize-null")
    extra_markers = set()
    for marker in args.null_marker:
        stripped_marker = marker.strip()
        if not stripped_marker:
            fail("--null-marker requires a value that is non-empty "
                 "after stripping surrounding whitespace")
        extra_markers.add(ascii_lower(stripped_marker))
    if args.rule == "normalize-null":
        rule = partial(normalize_null, extra_markers=extra_markers)

    # --date-order only governs normalize-date. argparse already rejects
    # a missing value or anything other than the lowercase choices dmy /
    # mdy (exit 2); an explicit order paired with another rule is rejected
    # here, while omitting the option leaves every rule on its default.
    if args.date_order is not None and args.rule != "normalize-date":
        fail("--date-order can only be used with --rule normalize-date")
    date_order = args.date_order or DEFAULT_DATE_ORDER
    if args.rule == "normalize-date":
        rule = partial(normalize_date, date_order=date_order)

    if os.path.abspath(args.input) == os.path.abspath(args.output):
        fail("output path must be different from the input path")
    if os.path.exists(args.output):
        fail(f"output file already exists: {args.output!r}")

    records = read_records(args.input)

    if not records or not records[0][1]:
        fail("input is empty: no header record")
    header = records[0][1]
    if any(name == "" for name in header):
        fail("header contains an empty column name")
    if len(set(header)) != len(header):
        fail("header contains duplicate column names")
    if args.column not in header:
        fail(f"column not found in header: {args.column!r}")
    column_index = header.index(args.column)

    expected_fields = len(header)
    out_rows = [header]
    data_rows = 0
    changed_cells = 0
    changes = []
    for record_no, record in records[1:]:
        if len(record) != expected_fields:
            fail(f"record {record_no} has {len(record)} field(s), "
                 f"expected {expected_fields}")
        record = list(record)
        try:
            cleaned = rule(record[column_index])
        except InvalidDateError:
            fail(f"invalid date in column {args.column!r} "
                 f"at record {record_no}: {record[column_index]!r}")
        if cleaned != record[column_index]:
            changes.append({
                "record": record_no,
                "column": args.column,
                "before": record[column_index],
                "after": cleaned,
            })
            record[column_index] = cleaned
            changed_cells += 1
        out_rows.append(record)
        data_rows += 1

    if not args.dry_run:
        try:
            with open(args.output, "x", encoding="utf-8", newline="") as outfile:
                csv.writer(outfile).writerows(out_rows)
        except FileExistsError:
            fail(f"output file already exists: {args.output!r}")
        except OSError as exc:
            try:
                os.unlink(args.output)
            except OSError:
                pass
            fail(f"cannot write output file {args.output!r}: {exc}")

    summary = {"rows": data_rows, "changed_cells": changed_cells}
    if args.include_changes:
        summary["changes"] = changes
    print(json.dumps(summary))


if __name__ == "__main__":
    main()

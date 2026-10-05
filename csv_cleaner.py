#!/usr/bin/env python3
"""Local CSV cleaner: apply one explicit rule to one column of a UTF-8 CSV.

Usage:
    python csv_cleaner.py --input input.csv --output cleaned.csv \
        --column name --rule trim

normalize-null additionally accepts repeatable custom null markers:

    python csv_cleaner.py --input input.csv --output cleaned.csv \
        --column name --rule normalize-null \
        --null-marker MISSING --null-marker 待补

normalize-null also accepts --null-replacement TEXT to substitute the
given text for every cell the rule would otherwise turn into an empty
string:

    python csv_cleaner.py --input input.csv --output cleaned.csv \
        --column name --rule normalize-null --null-replacement 未知

The replacement is written verbatim: it is not stripped, not
case-folded and never re-matched against the null markers, and an
empty or whitespace-only replacement is allowed. Omitting the option
keeps the default empty-string behavior. Cells whose value does not
match a marker are kept byte-for-byte either way, and a cell only
counts as changed when the replacement differs from its original
value.

The field delimiter is chosen explicitly with --delimiter:

    python csv_cleaner.py --input sample.csv --output cleaned.csv \
        --column name --rule trim --delimiter semicolon

    --delimiter accepts only the lowercase names comma, semicolon and
    tab, meaning a comma, a semicolon and one real tab character
    respectively; omitting it is the same as comma. The chosen
    delimiter is used both to read the input and to write the result,
    never guessed from the file contents.

    The export delimiter can be chosen independently with
    --output-delimiter:

    python csv_cleaner.py --input sample.csv --output cleaned.csv \
        --column name --rule trim --delimiter semicolon \
        --output-delimiter comma

    --output-delimiter accepts the same lowercase names comma,
    semicolon and tab. When given it overrides only the output format:
    the input is still read with --delimiter, and any of the three
    combinations is allowed. Omitting it keeps one shared delimiter for
    reading and writing (comma when --delimiter is also omitted). A
    change of delimiter is only a format change and never counts as a
    changed cell.

normalize-date additionally accepts --date-order to choose how a slash
date with the year last is read:

    python csv_cleaner.py --input input.csv --output cleaned.csv \
        --column due_date --rule normalize-date --date-order mdy

    --date-order accepts only lowercase dmy and mdy; omitting it is the
    same as dmy (DD/MM/YYYY). Under mdy the year-last slash date is read
    as MM/DD/YYYY, with ambiguous fields settled by the chosen order and
    no guessing or fallback. YYYY-MM-DD, YYYY/MM/DD, YYYY.MM.DD and the
    compact eight-digit YYYYMMDD stay year-month-day under either order.

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

With --include-null-matches (normalize-null only) the summary also gains
a "null_matches" array with one {"record", "column", "before"} entry per
cell the null rule matches, in record order, whether or not the
replacement actually changes the cell text; the exported CSV is
unaffected and no separate detail file is written. The two detail
switches are independent and may be used together.

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
# A dot date is always year-month-day; the two English periods are part
# of the spelling and --date-order never applies to it.
DATE_DOT_RE = re.compile(r"^([0-9]{4})\.([0-9]{2})\.([0-9]{2})$")
# A compact date is exactly eight ASCII digits with no separator, always
# read year-month-day; --date-order never applies to it.
DATE_COMPACT_RE = re.compile(r"^([0-9]{4})([0-9]{2})([0-9]{2})$")

# Accepted --date-order values: how to read a NN/NN/YYYY slash date.
DATE_ORDERS = ("dmy", "mdy")
DEFAULT_DATE_ORDER = "dmy"

# Accepted --delimiter / --output-delimiter names mapped to the actual
# one-character field delimiters. Each is always explicit: the input
# delimiter defaults to comma, and the output delimiter defaults to the
# input one; neither is ever sniffed.
DELIMITERS = {"comma": ",", "semicolon": ";", "tab": "\t"}
DEFAULT_DELIMITER_NAME = "comma"


class InvalidDateError(ValueError):
    """Raised when a cell is not an accepted calendar date."""


def ascii_lower(text):
    """Lowercase ASCII A-Z only; all other characters stay untouched."""
    return "".join(
        chr(ord(ch) + 32) if "A" <= ch <= "Z" else ch for ch in text
    )


def is_null_match(value, extra_markers=frozenset()):
    """Return True when the null rule would replace the cell.

    After stripping both ends, the cell matches when the result is empty
    or equals NULL / N/A (or any of the given extra markers)
    case-insensitively with respect to ASCII letters. Anything else
    (e.g. "NULLABLE") does not match.
    """
    stripped = value.strip()
    if not stripped:
        return True
    lowered = ascii_lower(stripped)
    return lowered in NULL_MARKERS or lowered in extra_markers


def normalize_null(value, extra_markers=frozenset(), replacement=""):
    """Normalize null markers to the replacement text (empty by default).

    After stripping both ends, the cell is replaced when the result is
    empty or matches NULL / N/A (or any of the given extra markers)
    case-insensitively with respect to ASCII letters. Anything else is
    returned byte-for-byte, including its surrounding whitespace (e.g.
    "NULLABLE" is not a marker). Extra markers are compared after
    str.strip() themselves; duplicate markers collapse into one match but
    never inflate the change count. The replacement is used verbatim: it
    is not stripped, not case-folded and never re-matched against the
    markers, and an empty or whitespace-only replacement is allowed.
    """
    if is_null_match(value, extra_markers):
        return replacement
    return value


# Accepted spellings that are always read year-month-day; the separator
# (or lack of one) is part of the spelling and they are never mixed
# within a value.
DATE_YMD_PATTERNS = (DATE_ISO_RE, DATE_YMD_SLASH_RE, DATE_DOT_RE,
                     DATE_COMPACT_RE)


def parse_date_fields(stripped, date_order):
    """Split an accepted date spelling into (year, month, day) ints.

    The four YYYY-first spellings always read year-month-day regardless
    of date_order. The year-last slash spelling NN/NN/YYYY follows the
    explicit order only: "dmy" reads it DD/MM/YYYY and "mdy" reads it
    MM/DD/YYYY, with no guessing or fallback. Returns None when stripped
    matches none of the accepted spellings.
    """
    for pattern in DATE_YMD_PATTERNS:
        match = pattern.match(stripped)
        if match:
            return tuple(int(part) for part in match.groups())
    match = DATE_SLASH_YEAR_RE.match(stripped)
    if match:
        first, second, year = (int(part) for part in match.groups())
        if date_order == "mdy":
            return year, first, second
        return year, second, first
    return None


def normalize_date(value, date_order=DEFAULT_DATE_ORDER):
    """Normalize an accepted date spelling to YYYY-MM-DD.

    After stripping both ends, an empty cell stays empty. Anything else
    must be exactly YYYY-MM-DD, YYYY/MM/DD, YYYY.MM.DD, the compact
    eight-digit YYYYMMDD or a slash date with the four-digit year last
    (NN/NN/YYYY), using ASCII digits, a four-digit year and two-digit
    month/day, and must be a real proleptic Gregorian calendar date in
    years 0001-9999; the result is always spelled YYYY-MM-DD.

    YYYY.MM.DD is always read year-month-day with two English periods;
    like YYYY-MM-DD, YYYY/MM/DD and the compact YYYYMMDD it is
    unaffected by date_order. The compact spelling is exactly eight
    ASCII digits with no separator, always four-digit year, two-digit
    month and two-digit day in that order, never guessed or swapped.
    The year-last slash date is read by the explicit date_order only:
    "dmy" reads it as DD/MM/YYYY and "mdy" as MM/DD/YYYY. Ambiguous
    values follow that order with no guessing or fallback (under mdy
    13/02/2024 means month 13 and is invalid). YYYY-MM-DD,
    YYYY/MM/DD, YYYY.MM.DD and YYYYMMDD are always year-month-day under
    either order. Internal whitespace, unpadded numbers, mixed
    separators, time suffixes and null markers such as NULL or N/A are
    invalid and raise InvalidDateError.
    """
    stripped = value.strip()
    if not stripped:
        return ""
    fields = parse_date_fields(stripped, date_order)
    if fields is None:
        raise InvalidDateError(f"invalid date: {value!r}")
    year, month, day = fields
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
    parser.add_argument("--null-replacement", default=None,
                        metavar="TEXT",
                        help="replacement text for normalize-null: every "
                             "cell the rule would turn into an empty "
                             "string is written as TEXT instead, verbatim "
                             "(not stripped, not case-folded, never "
                             "re-matched; empty and whitespace-only text "
                             "is allowed); omitting it keeps the default "
                             "empty-string behavior")
    parser.add_argument("--date-order", choices=DATE_ORDERS, default=None,
                        metavar="ORDER",
                        help="how to read a slash date with the year last "
                             "for normalize-date: dmy (DD/MM/YYYY, the "
                             "default when omitted) or mdy (MM/DD/YYYY); "
                             "YYYY-MM-DD, YYYY/MM/DD, YYYY.MM.DD and the "
                             "compact YYYYMMDD stay year-month-day under "
                             "either order")
    parser.add_argument("--delimiter", choices=sorted(DELIMITERS),
                        default=DEFAULT_DELIMITER_NAME,
                        metavar="NAME",
                        help="field delimiter for reading the input "
                             "(and for writing unless --output-delimiter "
                             "is given): comma (the default when "
                             "omitted), semicolon or tab (one real tab "
                             "character); the delimiter is never guessed "
                             "from the file")
    parser.add_argument("--output-delimiter", choices=sorted(DELIMITERS),
                        default=None,
                        metavar="NAME",
                        help="field delimiter for the exported file "
                             "only: comma, semicolon or tab (one real "
                             "tab character); the input is still read "
                             "with --delimiter, so any combination is "
                             "allowed; omitting it writes with the same "
                             "delimiter the input was read with")
    parser.add_argument("--include-changes", action="store_true",
                        help="add a changes array to the success summary "
                             "with one {record, column, before, after} "
                             "entry per changed cell, in record order")
    parser.add_argument("--include-null-matches", action="store_true",
                        help="add a null_matches array to the success "
                             "summary with one {record, column, before} "
                             "entry per cell the normalize-null rule "
                             "matches, in record order, whether or not "
                             "the replacement changes the cell text; "
                             "only valid with --rule normalize-null")
    parser.add_argument("--dry-run", action="store_true",
                        help="preview only: fully read and validate the "
                             "input and print the same summary JSON, but "
                             "create no output file or directory")
    return parser.parse_args(argv)


def read_records(path, delimiter):
    """Read all CSV records, returning a list of (record_number, fields).

    Record numbers start at 1 for the header; quoted newlines inside a
    field do not advance the number. The given delimiter is used
    exactly as provided and is never sniffed.
    """
    records = []
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as infile:
            reader = csv.reader(infile, delimiter=delimiter, strict=True)
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

    # argparse --delimiter choices already reject a missing value or
    # anything other than the lowercase names comma / semicolon / tab
    # (exit 2); the mapping gives the actual one-character delimiter
    # used for reading, with comma as the default.
    delimiter = DELIMITERS[args.delimiter]

    # --output-delimiter is validated by argparse the same way. When
    # given it overrides only the export format; when omitted the output
    # reuses the input delimiter (comma by default). A format change by
    # itself never counts as a changed cell.
    output_delimiter = (
        DELIMITERS[args.output_delimiter]
        if args.output_delimiter is not None
        else delimiter
    )

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

    # --null-replacement is only meaningful for normalize-null. argparse
    # already rejects a missing value (exit 2); any text is otherwise
    # accepted verbatim, including empty and whitespace-only strings.
    if args.null_replacement is not None and args.rule != "normalize-null":
        fail("--null-replacement can only be used with "
             "--rule normalize-null")
    if args.rule == "normalize-null":
        rule = partial(normalize_null, extra_markers=extra_markers,
                       replacement=args.null_replacement or "")

    # --include-null-matches only reports on normalize-null matches; with
    # any other rule it is rejected before the input is even read.
    if args.include_null_matches and args.rule != "normalize-null":
        fail("--include-null-matches can only be used with "
             "--rule normalize-null")

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

    records = read_records(args.input, delimiter)

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
    null_matches = []
    for record_no, record in records[1:]:
        if len(record) != expected_fields:
            fail(f"record {record_no} has {len(record)} field(s), "
                 f"expected {expected_fields}")
        record = list(record)
        original = record[column_index]
        # A null match is recorded against the original parsed text even
        # when the replacement leaves the cell byte-for-byte identical
        # (e.g. an empty cell with the default empty replacement, or a
        # marker spelled exactly like --null-replacement); the
        # replacement result itself is never re-matched.
        if args.include_null_matches and is_null_match(original,
                                                       extra_markers):
            null_matches.append({
                "record": record_no,
                "column": args.column,
                "before": original,
            })
        try:
            cleaned = rule(original)
        except InvalidDateError:
            fail(f"invalid date in column {args.column!r} "
                 f"at record {record_no}: {original!r}")
        if cleaned != original:
            changes.append({
                "record": record_no,
                "column": args.column,
                "before": original,
                "after": cleaned,
            })
            record[column_index] = cleaned
            changed_cells += 1
        out_rows.append(record)
        data_rows += 1

    if not args.dry_run:
        try:
            with open(args.output, "x", encoding="utf-8", newline="") as outfile:
                csv.writer(outfile,
                           delimiter=output_delimiter).writerows(out_rows)
        except FileExistsError:
            fail(f"output file already exists: {args.output!r}")
        except OSError as exc:
            try:
                os.unlink(args.output)
            except OSError:
                pass
            fail(f"cannot write output file {args.output!r}: {exc}")

    summary = {"rows": data_rows, "changed_cells": changed_cells}
    if args.include_null_matches:
        summary["null_matches"] = null_matches
    if args.include_changes:
        summary["changes"] = changes
    print(json.dumps(summary))


if __name__ == "__main__":
    main()

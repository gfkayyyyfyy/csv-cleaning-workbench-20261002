#!/usr/bin/env python3
"""Local CSV cleaner: apply one explicit rule to one column of a UTF-8 CSV.

Usage:
    python csv_cleaner.py --input input.csv --output cleaned.csv \
        --column name --rule trim

On success prints a single JSON object to stdout, e.g.
    {"rows": 3, "changed_cells": 2}
and exits 0. Any failure exits 2 with the reason on stderr and no output
file is created.
"""

import argparse
import csv
import json
import os
import sys

RULES = {
    "trim": str.strip,
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
    for record_no, record in records[1:]:
        if len(record) != expected_fields:
            fail(f"record {record_no} has {len(record)} field(s), "
                 f"expected {expected_fields}")
        record = list(record)
        cleaned = rule(record[column_index])
        if cleaned != record[column_index]:
            record[column_index] = cleaned
            changed_cells += 1
        out_rows.append(record)
        data_rows += 1

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

    print(json.dumps({"rows": data_rows, "changed_cells": changed_cells}))


if __name__ == "__main__":
    main()

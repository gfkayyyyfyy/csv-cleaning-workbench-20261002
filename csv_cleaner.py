#!/usr/bin/env python3
"""csv_cleaner.py — 本地 CSV 清洗入口。

读取 UTF-8 CSV（允许开头带 BOM），对指定的一列应用一条显式规则，
将结果导出为不带 BOM 的 UTF-8 CSV 新文件，并在标准输出打印 JSON 摘要。

当前仅支持 trim 规则：按 Python str.strip 语义删除单元格两端空白。

用法：
    python csv_cleaner.py --input input.csv --output cleaned.csv \
        --column name --rule trim

成功：退出码 0，标准输出为 {"rows": N, "changed_cells": M}。
失败：退出码 2，标准错误说明原因，不创建输出文件。
"""

import argparse
import csv
import io
import json
import os
import sys

SUPPORTED_RULES = ("trim",)


def fail(message):
    """打印错误原因到标准错误并以退出码 2 结束。"""
    print(f"错误: {message}", file=sys.stderr)
    sys.exit(2)


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="csv_cleaner.py",
        description="对 CSV 指定列应用一条清洗规则并导出新文件（当前仅支持 trim）。",
    )
    parser.add_argument("--input", required=True, help="输入 CSV 文件路径（只读）")
    parser.add_argument("--output", required=True, help="输出 CSV 文件路径（必须不存在）")
    parser.add_argument("--column", required=True, help="要处理的列名（按原文精确匹配）")
    parser.add_argument("--rule", required=True, help="清洗规则，当前仅支持 trim")
    # 缺少必需参数时 argparse 会以退出码 2 结束并输出原因，符合约定。
    return parser.parse_args(argv)


def read_records(path):
    """只读方式读取输入文件并解析为记录列表（首条为表头）。"""
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            content = f.read()
    except FileNotFoundError:
        fail(f"输入文件不存在: {path}")
    except UnicodeDecodeError as e:
        fail(f"输入文件不是有效的 UTF-8: {e}")
    except OSError as e:
        fail(f"读取输入文件失败: {e}")

    try:
        # strict=True 让未闭合引号等格式错误抛出 csv.Error。
        return list(csv.reader(io.StringIO(content), strict=True))
    except csv.Error as e:
        fail(f"CSV 无法解析: {e}")


def validate_header(header):
    if not header:
        fail("输入为空: 缺少表头")
    for name in header:
        if name == "":
            fail("表头包含空名称")
    seen = set()
    for name in header:
        if name in seen:
            fail(f"表头包含重复名称: {name!r}")
        seen.add(name)


def apply_trim(records, col_idx):
    """对目标列应用 trim，返回 (输出行, 发生变化的单元格数)。"""
    changed = 0
    out_rows = [records[0]]
    for row in records[1:]:
        new_row = list(row)
        original = new_row[col_idx]
        cleaned = original.strip()
        if cleaned != original:
            changed += 1
        new_row[col_idx] = cleaned
        out_rows.append(new_row)
    return out_rows, changed


def main(argv=None):
    args = parse_args(argv)

    if args.rule not in SUPPORTED_RULES:
        fail(f"不支持的规则: {args.rule!r}（当前仅支持: {', '.join(SUPPORTED_RULES)}）")

    # 输出只能写入新文件：拒绝与输入同路径或已存在的输出。
    if os.path.abspath(args.input) == os.path.abspath(args.output):
        fail("输出文件与输入文件指向同一路径，已拒绝执行")
    if os.path.exists(args.output):
        fail(f"输出文件已存在，为保留已有内容拒绝覆盖: {args.output}")

    records = read_records(args.input)
    if not records:
        fail("输入为空: 没有任何记录")

    header = records[0]
    validate_header(header)

    if args.column not in header:
        fail(f"指定列不存在: {args.column!r}")
    col_idx = header.index(args.column)

    # 校验每条数据记录的字段数；表头记为第 1 条，引号内换行不增加序号
    # （csv.reader 已把带引号换行的单元格合并为一条记录）。
    width = len(header)
    for rec_no, row in enumerate(records, start=1):
        if rec_no == 1:
            continue
        if len(row) != width:
            fail(f"第 {rec_no} 条记录的字段数为 {len(row)}，与表头的 {width} 不一致")

    out_rows, changed = apply_trim(records, col_idx)

    try:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerows(out_rows)
    except OSError as e:
        # 写入失败时尽量清理可能产生的半成品文件。
        try:
            os.remove(args.output)
        except OSError:
            pass
        fail(f"写入输出文件失败: {e}")

    print(json.dumps(
        {"rows": len(records) - 1, "changed_cells": changed},
        ensure_ascii=False,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())

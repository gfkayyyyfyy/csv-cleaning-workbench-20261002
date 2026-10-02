# CSV 数据清洗工作台

建设面向日常表格交换的本地数据整理产品，逐步覆盖 CSV 导入与预览、列类型与缺失值检查、字段标准化、规则去重、清洗步骤保存、结果导出和可追溯质量报告。

计划采用：Python 3 标准库 / csv / json / argparse。

## csv_cleaner.py — 本地 CSV 清洗入口

读取 UTF-8 CSV（允许开头带 BOM，首条记录为表头），对指定的一列应用一条显式规则，导出为不带 BOM 的 UTF-8 CSV 新文件，并在标准输出打印 JSON 摘要。仅依赖 Python 3 标准库。

### 用法

```bash
python csv_cleaner.py --input input.csv --output cleaned.csv --column name --rule trim
```

四个参数均需显式提供：

| 参数 | 说明 |
| --- | --- |
| `--input` | 输入 CSV 路径（始终保持只读） |
| `--output` | 输出 CSV 路径（必须不存在，且不能与输入同路径） |
| `--column` | 要处理的列名（按表头原文精确匹配，区分大小写） |
| `--rule` | 清洗规则，当前仅支持 `trim` |

`trim` 按 Python `str.strip` 语义删除所选列各单元格两端的空白，保留单元格内部空白；其他列内容、记录顺序、行数均不变，不做类型转换。

### 成功

退出码 0，标准输出仅一个 JSON 对象：

```json
{"rows": 3, "changed_cells": 2}
```

- `rows`：数据记录条数（不含表头）
- `changed_cells`：清理前后字符串发生变化的单元格数

### 失败

退出码统一为 2，标准输出为空，标准错误说明具体原因，且不创建输出文件。包括：缺少参数、规则不支持、指定列不存在、输入为空、表头有空名称或重复名称、数据记录字段数与表头不一致（诊断含从表头记为第 1 条的记录序号，引号内换行不增加序号）、CSV 无法解析、输入不存在、UTF-8 解码失败、读写失败、输出已存在或与输入同路径。

### 示例

仓库内 `input.csv` 为示例数据（表头 `name,note`，三条记录依次为 `" Alice ","x,y"`、`"   ",ok`、`Bob,z`）。执行上面的命令后：

- 标准输出：`{"rows": 3, "changed_cells": 2}`
- `cleaned.csv` 的 `name` 列依次为 `Alice`、空字符串、`Bob`，`note` 列保持 `x,y`、`ok`、`z` 不变

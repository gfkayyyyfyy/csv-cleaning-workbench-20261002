# CSV 数据清洗工作台

建设面向日常表格交换的本地数据整理产品，逐步覆盖 CSV 导入与预览、列类型与缺失值检查、字段标准化、规则去重、清洗步骤保存、结果导出和可追溯质量报告。

计划采用：Python 3 标准库 / csv / json / argparse。

## csv_cleaner.py：本地 CSV 清洗入口

对单个指定列应用一条显式规则，导出新文件并打印摘要。仅依赖 Python 3 标准库。

```bash
python csv_cleaner.py --input input.csv --output cleaned.csv --column name --rule trim
```

四个参数均为必填：

| 参数 | 说明 |
| --- | --- |
| `--input` | 输入 CSV 路径（逗号分隔、UTF-8、允许 BOM，首条记录为表头；只读，不会被修改） |
| `--output` | 输出 CSV 路径（必须是不存在的新文件，且不能与输入指向同一文件；输出为无 BOM 的 UTF-8 CSV） |
| `--column` | 要清洗的列名，与表头精确匹配（区分大小写），只选一列 |
| `--rule` | 清洗规则，当前仅支持 `trim`（按 `str.strip` 语义去除单元格两端空白，保留内部空白） |

成功时退出码为 0，标准输出只有一个 JSON 对象，例如 `{"rows": 3, "changed_cells": 2}`：
`rows` 为数据记录数（不含表头），`changed_cells` 为清理前后字符串发生变化的单元格数。
仅含表头的文件会成功导出表头，两项计数均为 0。

失败时退出码为 2，标准输出为空，标准错误说明原因，且不创建输出文件。包括：缺少参数、
规则不支持、列不存在、输入为空、表头含空名或重名、记录列数与表头不一致（报错含从表头
记为第 1 条开始的记录序号，引号内换行不计入）、CSV 无法解析、输入不存在、UTF-8 解码
失败、读写失败、输出已存在或与输入同路径（已有内容保留不变）。

### 示例

仓库根目录的 `input.csv`：

```csv
name,note
" Alice ","x,y"
"   ",ok
Bob,z
```

执行上面的命令后，标准输出为 `{"rows": 3, "changed_cells": 2}`，`cleaned.csv` 内容为：

```csv
name,note
Alice,"x,y"
,ok
Bob,z
```

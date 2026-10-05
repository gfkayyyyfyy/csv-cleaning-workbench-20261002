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
| `--input` | 输入 CSV 路径（分隔符由 `--delimiter` 显式指定，默认逗号；UTF-8、允许 BOM，首条记录为表头；只读，不会被修改） |
| `--output` | 输出 CSV 路径（必须是不存在的新文件，且不能与输入指向同一文件；输出为无 BOM 的 UTF-8 CSV） |
| `--column` | 要清洗的列名，与表头精确匹配（区分大小写），只选一列 |
| `--rule` | 清洗规则，当前支持 `trim`（按 `str.strip` 语义去除单元格两端空白，保留内部空白）、`normalize-null`、`normalize-date` 与 `normalize-whitespace`（见下） |

可选参数 `--delimiter NAME` 显式选择字段分隔符，仅接受小写名称 `comma`、
`semicolon` 和 `tab`，分别表示逗号、分号和一个实际制表符；省略时等同 `comma`。
所选分隔符同时用于读取输入和写出结果，不根据文件内容自动猜测（例如用
`semicolon` 读取逗号文件时，逗号只是字段内容的一部分）。除分隔符外的既有
CSV 规则不变：输入继续允许 UTF-8 BOM、输出为无 BOM 的 UTF-8，引号内的分隔符、
双引号与真实换行继续作为字段内容保留，表头、记录顺序和非目标列的解析后字符串
保持不变，引号内换行不计入记录序号。

```bash
python csv_cleaner.py --input sample.csv --output cleaned.csv \
    --column name --rule trim --delimiter semicolon
```

例如 `sample.csv` 表头为 `name;note`，三条记录依次为 `" Alice ";"x;y"`、
`"   ";ok` 和 `Bob;z`：以 `--delimiter semicolon` 对 `name` 列执行 `trim` 时，
摘要为 `{"rows": 3, "changed_cells": 2}`，`--include-changes` 的 `changes`
只按顺序列出记录 2 和 3，`before` 分别为 `" Alice "` 和 `"   "`、`after`
分别为 `Alice` 和空字符串；导出文件仍用分号分隔，备注 `x;y` 仍是一个字段。

`normalize-null`：先按 `str.strip` 去掉两端空白，若结果为空，或与 `NULL`、`N/A`
做忽略 ASCII 字母大小写的完整匹配，则结果为空字符串；未命中时保留原字符串
（包括两端空白），普通文本中包含标记不会被判为空，例如 `NULLABLE` 保持不变。

可重复提供的可选参数 `--null-marker MARKER` 仅在 `--rule normalize-null` 时
可用，用于为本次运行的指定列追加整值空值标记。标记本身与目标单元格都先按
`str.strip` 去除两端空白，再做仅忽略 ASCII 字母大小写的精确整值匹配（不做
包含、前缀或正则匹配）；命中后输出空字符串，未命中则保留原单元格（包括两端
空白）。重复提供或与默认 `NULL`、`N/A` 等价的标记会被去重，不会重复统计变化；
默认的空值、`NULL`、`N/A` 处理始终保留。标记值在 `str.strip` 后为空、缺值，或
与 `trim`、`normalize-date` 配合使用时，按参数错误处理（退出码 2）。

可选参数 `--null-replacement TEXT` 仅在 `--rule normalize-null` 时可用，把本次运行
中原本会被该规则转为空字符串的单元格（原本为空或纯空白的值、默认 `NULL` 与 `N/A`，
以及 `--null-marker` 追加的整值标记命中项）改写为参数原文。匹配方式与未提供该参数
时完全一致，未命中的值连同两端空白原样保留；替代文本不去空白、不改大小写、写出后
不再参与标记识别，空字符串与纯空白文本也允许使用。省略该参数时保持既有行为（转为
空字符串）。摘要仍只统计实际字符串变化：替代文本与原值相同的单元格不计入
`changed_cells`，开启 `--include-changes` 时也不收录。`--null-replacement` 缺值，或
与 `trim`、`normalize-date`、`normalize-whitespace` 配合使用时，按参数错误处理
（退出码 2，仅含表头时同样拒绝）。

`normalize-date`：先按 `str.strip` 去掉两端空白，空字符串或纯空白输出为空；其余
接受 `YYYY-MM-DD`、`YYYY/MM/DD`、`YYYY.MM.DD`、无分隔符的八位紧凑写法
`YYYYMMDD` 与四位年份在末尾的斜杠日期五种写法（同一列可混用），要求 ASCII
数字、四位年份、两位月日及与写法对应的分隔符（`-`、`/` 或两个英文句点 `.`；
紧凑写法不含分隔符，恰好八个数字），且为公历 0001 至 9999 年内的真实日期，结果
统一输出为 `YYYY-MM-DD`（例如 `2024/02/29` 变为 `2024-02-29`，
`2024.02.29` 同样变为 `2024-02-29`，`20240229` 变为 `2024-02-29`，
`0001/01/01` 变为 `0001-01-01`）。
点分隔写法与紧凑写法一律按年月日解释，与 `--date-order` 无关，也没有年份在末尾
的点写法；紧凑写法的月日固定为第 5-6、7-8 位，不交换也不猜测。
年末斜杠日期的月日顺序由可选参数 `--date-order ORDER` 显式选择：仅接受小写
`dmy` 与 `mdy`，省略时等同 `dmy`，即保持既有的 `DD/MM/YYYY` 解释；`mdy` 把该
写法解释为 `MM/DD/YYYY`。歧义值一律按所选顺序确定，不猜测也不回退（例如 `mdy`
下 `13/02/2024` 是月份 13，`02/30/2024` 是 2 月 30 日，均为非法日期）。
`YYYY-MM-DD`、`YYYY/MM/DD`、`YYYY.MM.DD` 与 `YYYYMMDD` 在两种顺序下均按年月日
解释，与 `--date-order` 无关。内部空白、未补零的月日、混用分隔符（如
`2024-02.29`、`01.02.2024`）、七位或九位数字、全角数字（含全角句点 `。`）、
时间后缀以及 `NULL`、`N/A` 等文本均为非法日期（紧凑写法下如 `20230229`、
`00000101` 同样非法）：目标列出现非法日期时按记录顺序报告首个错误（含列名与记录
序号），退出码为 2，不创建输出文件。

`normalize-whitespace`：把单元格整理为单行且词间只有一个空格。空白按
`str.isspace` 判定（含制表符、回车、换行及全角空格 U+3000 等）：去掉两端空白，
内部每段连续空白替换为一个 ASCII 空格。空字符串不变，纯空白变为空字符串，其余
字符及顺序保留（包括 `str.isspace` 不视为空白的零宽空格 U+200B）。`NULL`、`N/A`
与日期文本只处理空白，不做额外转换。该规则与 `--null-marker`、`--date-order`
不兼容：显式搭配任一参数按参数错误处理（退出码 2，仅含表头时同样拒绝）。

成功时退出码为 0，标准输出只有一个 JSON 对象，例如 `{"rows": 3, "changed_cells": 2}`：
`rows` 为数据记录数（不含表头），`changed_cells` 为清理前后字符串发生变化的单元格数。
仅含表头的文件会成功导出表头，两项计数均为 0。

可选开关 `--include-changes`（不带值）让同一个 JSON 对象增加 `changes` 数组，不另写
明细文件，导出的 CSV 与不加开关时完全一致。`changes` 只收录目标列清洗前后字符串不同
的单元格，每项含 `record`（记录序号，表头记为 1，引号内换行不计入）、`column`（目标
列名）、`before`（解析后的原字符串，含两端空白与实际换行）、`after`（写入结果的字符
串）；按记录顺序排列，每项只出现一次，长度等于 `changed_cells`。原本为空且未变化的值
不收录，纯空白变为空字符串则收录；仅含表头或没有变化时 `changes` 为 `[]`。

失败时退出码为 2，标准输出为空，标准错误说明原因，且不创建输出文件。包括：缺少参数、
规则不支持、列不存在、输入为空、表头含空名或重名、记录列数与表头不一致、目标列含非法
日期（报错含列名与从表头记为第 1 条开始的记录序号，引号内换行不计入）、CSV 无法解析、
输入不存在、UTF-8 解码失败、读写失败、输出已存在或与输入同路径（已有内容保留不变）、
`--null-marker` 缺值、去空白后为空或与非 `normalize-null` 规则配合使用、
`--null-replacement` 缺值或与非 `normalize-null` 规则配合使用、
`--date-order` 缺值、取值不是小写 `dmy`/`mdy` 或显式与 `trim`、
`normalize-null`、`normalize-whitespace` 配合使用（仅含表头时同样拒绝无效参数；参数有效时仅含表头的
文件正常导出表头）、
`--delimiter` 缺值、为空或取值不是小写 `comma`/`semicolon`/`tab`
（仅含表头时同样拒绝；合法参数下仅含表头的文件按同一分隔符导出表头，
计数为零，开启明细时 `changes` 为 `[]`）。

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

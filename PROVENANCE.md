# 本地模型新增文件清单（PROVENANCE）

**这些文件不是项目作者手写的，由本地模型（DeepSeek Harness 会话助手）于 2026-10-21 添加。**

项目作者原有的任何文件均未被修改：`git status --short` 只显示 `??`（未跟踪新增），没有 `M`。

## 清单

| 文件 | 性质 | 标注方式 | sha256 |
|---|---|---|---|
| `docs\review-gaps-20261021.md` | 第三方评审：8 个缺口与补法 | 文本横幅 | `4bca2c722f5d4410…` |
| `evals\badcase-taxonomy.md` | 失败归因分类 + 金标核对记录模板 | 文本横幅 | `b2b5442cb0854ba9…` |
| `evals\smoke-10-draft.jsonl` | 10 条冒烟评测题草稿（锚点需作者复核） | 每条 _provenance 字段 | `d37df7b7e6b9365b…` |
| `examples\format-fixtures\README.md` | 格式夹具说明与期望解析行为 | 文本横幅 | `ef4d0929447fc97c…` |
| `examples\format-fixtures\_make_fixtures.py` | 夹具生成脚本 | 脚本顶部注释横幅 | `5fed63a0b2a3bf25…` |
| `examples\format-fixtures\fixture-messy.txt` | 脏格式 TXT 夹具 | 文件首行标注（BOM 之后） | `01633a07fe88f99f…` |
| `examples\format-fixtures\fixture-table.docx` | 跨页表格夹具源文件 | 核心属性 author/comments/category | `4858fd00763b71fd…` |
| `examples\format-fixtures\fixture-table.pdf` | 跨页表格 + 页眉页脚夹具 | PDF 文档信息 /Author /Comments | `4ccf4ba3b94d7978…` |
| `examples\format-fixtures\fixture-scanned.docx` | 无文本层夹具源文件 | 核心属性 author/comments/category | `7c53bc673260d385…` |
| `examples\format-fixtures\fixture-scanned.pdf` | 无文本层（扫描样）夹具 | PDF 文档信息 /Author /Comments | `f6a27b4895e546c8…` |

> 本文件不含自身哈希。校验时对上述 10 个文件重新计算 sha256 并与本表比对；若项目作者改写某个文件，哈希会变，应同时更新或删除对应标注行。

## 标注方式说明

- **文本类（.md/.py/.txt）**：文件顶部有「来源标注」横幅；`fixture-messy.txt` 的横幅位于 BOM 之后，不影响 BOM 考点。
- **JSONL**：每条记录含 `_provenance` 字段，标明由本地模型添加、锚点需作者本人复核。
- **DOCX**：核心属性 `author`、`last_modified_by`、`comments`、`category` 已写入来源信息。
- **PDF**：文档信息 `/Author`、`/Title`、`/Subject`、`/Keywords`、`/Creator`、`/Comments` 已写入来源信息，`/Producer` 追加了 `local-model-added`。

## 采纳建议

- 采纳的结论可改写为项目作者自己的表述并移除标注；**未采纳的文件建议保留标注或直接删除**，不要让评审稿混进自己的设计文档。
- `evals/smoke-10-draft.jsonl` 的 gold 锚点由本地模型阅读语料后填写，**必须作者本人复核**后才能纳入评测集。

---

## 2026-10-24 复核与采纳记录（ZCode/GLM 会话，经项目作者授权）

- 上述 10 个文件的 sha256 已全部重算比对，与本表一致，文件未被改动。
- `examples/public-docs/` 已改名 `examples/synthetic-docs/`；本文件与评审文件中的旧路径按历史记录保留，不回溯修改。
- 采纳情况：缺口 1 → 任务清单新增 S1-T12（语料干扰扩充，检索基线前）；缺口 2 → S0-T07/S1-T10 增加“计算/澄清/干扰类单列口径”；缺口 3、5 → `evals/badcase-taxonomy.md` 纳入规范、S0-T07 条件 7 增加金标核对记录模板要求；缺口 4 → 任务清单新增 S1-T13（夹具 fail-loud 断言；夹具声明已实测复核，见 `evals/fixture-check-20261024.md`）；缺口 6 → 新增 S4-T05 上线后监控与回流设计；缺口 7 → 目录改名完成；缺口 8 → README 增“开发方法”一节。
- `evals/smoke-10-draft.jsonl` 已完成机器校验（见 `evals/anchor-check-20261024.md`），**作者本人复核仍待完成**，尚未采纳为正式评测集。
- 有一处措辞出入待作者定夺：PDF 夹具的 `/Title`、`/Subject` 实测为描述性内容，不含来源标注（详见夹具复核报告）；若修订本文件，需同步更新上表哈希。
- 详细改动清单与交接说明见 `docs/worklog-20261024-zcode.md`。

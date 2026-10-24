# 格式夹具实测复核报告（2026-10-24）

> 执行：ZCode/GLM 会话（经用户授权）。方法：`evals/tools/check_fixtures.py`（pypdf 6.21.2 + 标准库，不联网、不修改被检文件），复核对象为 `examples/format-fixtures/README.md` 第 2 节「已实测事实」与 `PROVENANCE.md` 中关于夹具元数据的声明。本报告是机器复核记录，不构成作者人工验收。

## 结论

**53 项断言全部通过**（2026-10-24，仓库工作区状态）。README 第 2 节的实测事实与 PROVENANCE 的夹具标注声明基本属实；发现 1 处措辞出入（见「不符与修正记录」第 1 条），不影响夹具可用性。

## 逐项结果（声称 vs 实测摘要）

### fixture-table.pdf（跨页表格 + 页眉页脚）

| 声称 | 实测 | 结果 |
|---|---|---|
| 共 2 页 | 页数 = 2 | PASS |
| 表格跨页，L30 只在第 2 页 | 第 1 页行 L1–L18 共 18 行；第 2 页行 L19–L30 共 12 行；L30 仅在第 2 页 | PASS |
| 表头行每页重复（tblHeader） | 「必需材料/对应处理时限/依据条款」两页均出现；docx 的 `word/document.xml` 含 `w:tblHeader` | PASS |
| 页眉「阶段交付与验收规则（A 库）— 合成演示夹具 — 内部编号 FIXTURE-A-001」逐页被抽取 | 两页均出现 | PASS |
| 页脚「第 N 页 / 共 2 页」被抽取 | 两页均出现 | PASS |
| 第 1 页约 1190、第 2 页约 784 可抽取字符 | 与声称偏差 ≤5%（最接近口径，精确值见脚本输出） | PASS |

### fixture-scanned.pdf（无文本层）

| 声称 | 实测 | 结果 |
|---|---|---|
| 共 1 页 | 页数 = 1 | PASS |
| 可抽取文本 0 字符 | `extract_text()` 去空白后长度 = 0 | PASS |
| 含 1 张图片 | 1 个图片 XObject：`/Im4`，1020×656，`/DCTDecode`（JPEG） | PASS |

### fixture-messy.txt（脏格式）

| 声称 | 实测 | 结果 |
|---|---|---|
| UTF-8 BOM 开头 | 前 3 字节 `ef bb bf` | PASS |
| 含 `\r\n` 换行 | 存在（脚本同时统计孤立 `\n`） | PASS |
| 全角混排 | `ＨＲＣ６０`、`ＨＶ３００`、`３个工作日`、`２０２６-１０-２１` 均存在 | PASS |
| 条款编号被换行切断（`A-X-` 换行 `13`） | 存在；**切断分隔符实测为 `\r\r\n`（连续两个 CR + LF），比 README 所写更脏** | PASS |
| （对照）连续 `A-X-13` 仅出现 1 次，即说明句「重组为 A-X-13 而不是两条」 | 符合 | PASS |
| PROVENANCE：来源横幅位于 BOM 之后（首行） | 首行含「来源标注」 | PASS |

### DOCX / PDF 来源元数据（PROVENANCE 声明）

- DOCX（两份）：`dc:creator` = 本地模型（DeepSeek Harness 会话助手，非项目作者本人）；`cp:category` = `synthetic-fixture / local-model-added`；`cp:lastModifiedBy`、comments 对应字段（`dc:description`）均含来源标注。PASS。
- PDF（两份）：`/Author`、`/Keywords`（`synthetic;local-model-added;format-fixture`）、`/Creator`（`local-model (DeepSeek Harness)`）、`/Comments`（完整来源标注句）均含来源信息；`/Producer` = `LibreOfficeDev 26.8.0.3 (X86_64) | local-model-added`。PASS。
- PROVENANCE sha256 清单（7 个夹具文件前 16 位前缀）：全部一致。PASS。

## 不符与修正记录

1. **PROVENANCE 措辞出入（唯一实质发现）**：PROVENANCE 称 PDF 的 `/Author /Title /Subject /Keywords /Creator /Comments`「已写入来源信息」，实测 `/Title` = `fixture-table`、`/Subject` = `synthetic format fixture`，是描述性内容、不含来源标注。不影响溯源链条（Author/Keywords/Creator/Comments/Producer 已足够），但 PROVENANCE 该行措辞偏宽。处置：本报告如实记录；PROVENANCE 由项目作者决定是否修订措辞（修订会使该文件哈希变化，需同步更新清单）。
2. **脚本两处断言初版误判（已修正，非夹具问题）**：初版用去空白文本匹配行号，导致 `L30` 与上一行 `A-R-02` 粘连、负向断言全部漏配；`A-X-13` 的切断分隔符按 `\r\n` 检查而实测为 `\r\r\n`。均已修正为上述通过版本。修正后的脚本对同类检查有可复用价值。
3. **对 S1-T13 的输入**：`fixture-messy.txt` 中 `\r\r\n` 是比预期更脏的换行样本，解析器的换行规范化断言应覆盖 CR、CRLF、CR CRLF 混合；`fixture-scanned.pdf` 的图片为 JPEG（`/DCTDecode`），无文本层考点成立。

## 复跑方式

```bash
.venv/Scripts/python.exe evals/tools/check_fixtures.py
# 退出码 0 = 全部通过；1 = 存在 FAIL（fail-loud）
```

# 失败题归因报告（B1）

> 数据：正式 A/B 六轮（vector/hybrid × 3）。系统性失败 = 同题同模式 ≥2/3 轮非 pass。
> 机械归因规则：金标不在 top-20 → R1；在 top-20 不在 top-5 → R2；在 top-5 → G 类（生成/口径侧，需人工细分）。

| 模式 | 题 | 类别 | 集合 | 预期 | 3 轮状态 | 归因 | 答案摘录 |
|---|---|---|---|---|---|---|---|
| vector | m04 | 事实 | dev | answer | status→status→status | R2（金标在候选但未进 top-5） |  |
| vector | m15 | 事实 | dev | answer | status→status→pass | R2（金标在候选但未进 top-5） | 验收期从完整交付的次一工作日起算3个工作日，只数周一至周五，截止第3日18:00（Asia/Shanghai）。 周五提交需先确认完成时间是否在当日18:00前 |
| vector | m36 | 跨文档 | dev | answer | status→status→pass | G*（证据已进 top-5，生成/口径侧失败） |  |
| vector | m57 | 版本 | freeze | answer | pass→status→status | R1（金标不在 top-20 候选） |  |
| vector | m59 | 版本 | dev | answer | status→status→status | G*（证据已进 top-5，生成/口径侧失败） |  |
| vector | m67 | 澄清 | dev | clarify | status→status→status | R1（金标不在 top-20 候选） | 接收方应从完整交付的次一工作日起 3 个工作日内给出验收意见。 |
| vector | m68 | 澄清 | dev | clarify | status→status→status | G*（证据已进 top-5，生成/口径侧失败） | 阶段交付的验收期按工作日计算，从完整交付的次一工作日起数满3个工作日，只数周一至周五，周六周日不计。 |
| vector | m69 | 澄清 | freeze | clarify | status→status→status | G*（证据已进 top-5，生成/口径侧失败） |  |
| hybrid | m19 | 事实 | freeze | answer | status→status→status | G*（证据已进 top-5，生成/口径侧失败） | 退回意见应逐项写明未满足的验收项与理由，交付方按意见补正后重新提交。 供应商整改后再次提交时，材料应包含验收单编号、问题截图、原因分析、修正后成果、遗留风险说明 |
| hybrid | m21 | 事实 | freeze | answer | status→status→status | R2（金标在候选但未进 top-5） |  |
| hybrid | m36 | 跨文档 | dev | answer | status→status→status | G*（证据已进 top-5，生成/口径侧失败） |  |
| hybrid | m38 | 跨文档 | dev | answer | status→pass→status | G*（证据已进 top-5，生成/口径侧失败） |  |
| hybrid | m47 | 跨文档 | freeze | answer | status→status→pass | G*（证据已进 top-5，生成/口径侧失败） | C 库供应商提交前需自检成果链接可打开、交付说明写清范围与变更点、验收对照表与成果逐条对应。 提交前任一项缺失时，先补齐再提交。 |
| hybrid | m57 | 版本 | freeze | answer | status→status→status | R1（金标不在 top-20 候选） | 草案未生效，当前一律按 v2 的 3 个工作日回答。 v3 草案数值仍可能调整，现稿未明确其相对 v2 的具体变更。 草案生效前已在途验收涉及旧提交时，应确认适 |
| hybrid | m58 | 版本 | freeze | answer | status→status→status | R2（金标在候选但未进 top-5） |  |
| hybrid | m67 | 澄清 | dev | clarify | status→status→status | R2（金标在候选但未进 top-5） | 接收方应从完整交付的次一工作日起 3 个工作日内给出验收意见。 |
| hybrid | m68 | 澄清 | dev | clarify | status→status→status | G*（证据已进 top-5，生成/口径侧失败） | 阶段交付的验收期按工作日计算，不是自然日；接收方应从完整交付的次一工作日起 3 个工作日内给出意见，截止时点为最后一日 18:00（Asia/Shanghai） |
| hybrid | m69 | 澄清 | freeze | clarify | status→status→status | G*（证据已进 top-5，生成/口径侧失败） |  |

## 汇总
- G*（证据已进 top-5，生成/口径侧失败）: vector/m36, vector/m59, vector/m68, vector/m69, hybrid/m19, hybrid/m36, hybrid/m38, hybrid/m47, hybrid/m68, hybrid/m69
- R1（金标不在 top-20 候选）: vector/m57, vector/m67, hybrid/m57
- R2（金标在候选但未进 top-5）: vector/m04, vector/m15, hybrid/m21, hybrid/m58, hybrid/m67

## 修复方向

- R1/G 类（m36 等）：检索不足——进入 B2 参数扫描与 B4 查询扩展的验证对象；
- G2（m67/m68 应澄清未澄清，两模式一致）：契约 v2.1 仍未覆盖的澄清形态，进入提示词 v3 迭代；
- hybrid 特有失败（m57/m58/m19/m21）：BM25+RRF 引入的候选扰动——若阶段 B2 调参无法挽回，维持向量为默认模式的决策。

注：归因为机械规则 + 人工复核摘要；G 类细分（G1/G2/G3）需人工确认语义。

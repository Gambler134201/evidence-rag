# 正式 A/B 对照报告：vector vs hybrid（冻结主集 80 条，每题 n=3，真实模型）

> 运行日期：见各 config-snapshot.json。数据集 `evals/datasets/main-80.jsonl`（已冻结）。
> A=精确向量；B=向量+BM25(jieba)+RRF(k=60)。六轮运行原始记录见 formal-ab/ 各子目录。
> 稳定性口径：同一题 3 次运行状态全部一致记「稳定」；headline 通过率以**留出集（freeze 40 条）**为准，开发集（dev 40）仅用于观察。

## 模式 vector（3 轮）

- 第 1 轮：通过 71/80，P50 8.5s，P95 50.8s
- 第 2 轮：通过 70/80，P50 9.7s，P95 51.3s
- 第 3 轮：通过 71/80，P50 9.2s，P95 53.7s

## 模式 hybrid（3 轮）

- 第 1 轮：通过 69/80，P50 10.0s，P95 39.5s
- 第 2 轮：通过 69/80，P50 8.9s，P95 45.6s
- 第 3 轮：通过 69/80，P50 10.4s，P95 33.8s

## 稳定题与不稳定题（按 3 轮状态一致性）

- vector 不稳定题：m14, m15, m36, m42, m57, m59, m60, m74
- hybrid 不稳定题：m38, m47, m59, m74

## 分集合通过率（3 轮中至少 2 轮通过记「稳定通过」）

| 集合 | vector 稳定通过 | hybrid 稳定通过 |
|---|---|---|
| dev | 34/40 | 36/40 |
| freeze | 37/40 | 33/40 |

## 逐题明细

| 题 | 类别 | 集合 | v-r1 | v-r2 | v-r3 | h-r1 | h-r2 | h-r3 |
|---|---|---|---|---|---|---|---|---|
| m01 | 事实 | dev | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m02 | 事实 | dev | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m03 | 事实 | dev | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m04 | 事实 | dev | insufficient_evidence | insufficient_evidence | insufficient_evidence | ✓ | ✓ | ✓ |
| m05 | 事实 | dev | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m06 | 事实 | dev | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m07 | 事实 | dev | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m08 | 事实 | freeze | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m09 | 事实 | dev | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m10 | 事实 | dev | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m11 | 事实 | dev | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m12 | 事实 | dev | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m13 | 事实 | freeze | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m14 | 事实 | dev | needs_clarification | ✓ | ✓ | ✓ | ✓ | ✓ |
| m15 | 事实 | dev | needs_clarification | needs_clarification | ✓ | ✓ | ✓ | ✓ |
| m16 | 事实 | dev | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m17 | 事实 | freeze | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m18 | 事实 | freeze | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m19 | 事实 | freeze | ✓ | ✓ | ✓ | needs_clarification | needs_clarification | needs_clarification |
| m20 | 事实 | freeze | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m21 | 事实 | freeze | ✓ | ✓ | ✓ | insufficient_evidence | insufficient_evidence | insufficient_evidence |
| m22 | 事实 | freeze | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m23 | 事实 | freeze | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m24 | 事实 | freeze | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m25 | 事实 | freeze | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m26 | 事实 | freeze | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m27 | 事实 | freeze | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m28 | 事实 | dev | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m29 | 事实 | freeze | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m30 | 事实 | freeze | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m31 | 跨文档 | freeze | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m32 | 跨文档 | dev | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m33 | 跨文档 | dev | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m34 | 跨文档 | dev | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m35 | 跨文档 | dev | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m36 | 跨文档 | dev | insufficient_evidence | insufficient_evidence | ✓ | insufficient_evidence | insufficient_evidence | insufficient_evidence |
| m37 | 跨文档 | dev | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m38 | 跨文档 | dev | ✓ | ✓ | ✓ | needs_clarification | ✓ | error |
| m39 | 跨文档 | dev | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m40 | 跨文档 | freeze | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m41 | 跨文档 | freeze | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m42 | 跨文档 | freeze | ✓ | needs_clarification | ✓ | ✓ | ✓ | ✓ |
| m43 | 跨文档 | freeze | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m44 | 跨文档 | freeze | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m45 | 跨文档 | freeze | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m46 | 跨文档 | freeze | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m47 | 跨文档 | freeze | ✓ | ✓ | ✓ | needs_clarification | needs_clarification | ✓ |
| m48 | 跨文档 | freeze | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m49 | 跨文档 | dev | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m50 | 跨文档 | dev | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m51 | 版本 | dev | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m52 | 版本 | dev | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m53 | 版本 | dev | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m54 | 版本 | freeze | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m55 | 版本 | freeze | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m56 | 版本 | freeze | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m57 | 版本 | freeze | ✓ | needs_clarification | needs_clarification | needs_clarification | needs_clarification | needs_clarification |
| m58 | 版本 | freeze | ✓ | ✓ | ✓ | insufficient_evidence | insufficient_evidence | insufficient_evidence |
| m59 | 版本 | dev | insufficient_evidence | insufficient_evidence | needs_clarification | ✓ | insufficient_evidence | ✓ |
| m60 | 版本 | dev | ✓ | ✓ | needs_clarification | ✓ | ✓ | ✓ |
| m61 | 无答案 | dev | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m62 | 无答案 | freeze | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m63 | 无答案 | freeze | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m64 | 无答案 | dev | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m65 | 无答案 | dev | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m66 | 无答案 | freeze | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m67 | 澄清 | dev | answered | answered | answered | answered | answered | answered |
| m68 | 澄清 | dev | answered | answered | answered | answered | answered | answered |
| m69 | 澄清 | freeze | insufficient_evidence | insufficient_evidence | insufficient_evidence | insufficient_evidence | insufficient_evidence | insufficient_evidence |
| m70 | 澄清 | freeze | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m71 | 干扰 | freeze | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m72 | 干扰 | dev | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m73 | 干扰 | dev | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m74 | 干扰 | freeze | ✓ | ✓ | needs_clarification | ✓ | ✓ | needs_clarification |
| m75 | 干扰 | freeze | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m76 | 权限 | freeze | 占位 | 占位 | 占位 | 占位 | 占位 | 占位 |
| m77 | 干扰 | freeze | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m78 | 干扰指令 | dev | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m79 | 干扰 | dev | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| m80 | 干扰 | dev | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

## 结论（2026-10-25 主会话基于六轮原始记录出具）

**核心数字（留出集 40 条，3 轮一致）：**

| 指标 | A 精确向量 | B 向量+BM25+RRF |
|---|---|---|
| Evidence Recall@5（锚点级） | **81.0%**（51/63） | 74.6%（47/63） |
| 稳定通过率（3 轮中 ≥2 轮 pass） | **92.5%**（37/40） | 82.5%（33/40） |
| Recall 三轮波动 | 0.0pp | 0.0pp |
| 回答时延 P50 | 8.5~9.7s | 8.9~10.4s |

**判断：A 胜出，混合检索在本语料上不保留为默认模式**（`retrieval_mode` 保留为可切换实验能力）。原因分析：语料的语义近邻干扰文档与正确文档**共享大量词汇**，BM25 通道同样被干扰项吸引，RRF 融合反而稀释了向量通道的强命中——这正是语料设计 30%+ 近邻干扰要制造的效果。原规划"不预设 B 一定更好"的判断被实测验证。

**Recall 81.0% 落在语料有效性区间（60~85%）内**：评测集具备区分度；距 85% 门槛的差距构成下一轮优化素材（m04/m36/m57/m58/m59 等系统性失败题，见逐题明细）。

**系统性问题清单（3 轮一致，非波动）**：m67/m68 应澄清却回答（两种模式一致，G2 生成侧）；m69 过度拒答；m36 检索不足；m57/m58/m19/m21 为模式特定失败（hybrid 过度澄清/拒答）。

**规模声明**：单项目小样本，数字不外推为企业准确率；正式报告原始记录见本目录各 raw.jsonl。

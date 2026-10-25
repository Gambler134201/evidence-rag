# evals/results/ 实验结果总索引

本目录是本项目全部评测运行记录与分析报告的唯一存放处。每条索引给出：是什么、
运行日期、关键数字（均抄自各 `report.md` / `config-snapshot.json`，不在本文件重算）、
复跑命令。各目录内 `raw.jsonl` 为逐题原始记录（每行含 `run_id`，可回查 dev 库
`query_runs` / `query_run_evidence` 表），`config-snapshot.json` 为运行时配置快照。

日期说明：目录条目的运行日期取自 `config-snapshot.json` 的 UTC 时间戳；
单独 `.md` 报告的日期取自文件头或对应提交（本地时区 UTC+8）。

## 条目索引

### stage1-baseline/ — 阶段 1 冒烟基线（草稿题）

- **是什么**：首次真实链路冒烟：精确向量检索（bge-m3 真实 Embedding）+ 本地端点生成，
  由 `run_smoke_baseline.py` 产出（含首次语料入库）。
- **运行日期**：2026-10-24T12:06 UTC。
- **数据**：`evals/smoke-10-draft.jsonl`（草稿 10 条，复核点未经作者确认；smk-05 权限占位跳过）；
  语料 17 份文档 / 187 chunk（kb-a 11、kb-b 3、kb-c 3）。
- **关键数字**：pass 7（smk-01/02/04/06/08/09/10）、R1 1（smk-03，历史版本未发布属设计行为）、
  G\* 1（smk-07）、占位 1。报告自述"基线观察，非准确率结论"。
- **复跑**：`ENABLE_REAL_MODEL_CALLS=1 .venv/Scripts/python.exe evals/tools/run_smoke_baseline.py`

### ab-vector/ 与 ab-hybrid/ — 首次正式 A/B（smoke-10 正式版）

- **是什么**：作者复核转正版冒烟集上的 A（精确向量）/ B（向量+BM25(jieba)+RRF k=60）对照，
  由 `run_eval.py --skip-ingest` 产出。
- **运行日期**：2026-10-24T13:41（A）/ 2026-10-24T13:44（B）UTC。
- **关键数字**：A 通过 7/9（G\*: smk-07/10）；B 通过 6/9（G\*: smk-07/10，R1: smk-03）。
  汇总见 ab-comparison-report.md：金标 Recall@5（锚点级，可执行题）A 11/14、B 12/14；
  时延 A P50 7.8s / max 37.6s，B P50 8.9s / max 47.8s。
- **复跑**：`ENABLE_REAL_MODEL_CALLS=1 .venv/Scripts/python.exe evals/tools/run_eval.py --dataset evals/datasets/smoke-10.jsonl --mode vector --name ab-vector --skip-ingest`（B 把 `--mode` 换 `hybrid`、`--name` 换 `ab-hybrid`）

### ab-comparison-report.md — 冒烟集 A/B 对照分析（手写）

- **是什么**：对 ab-vector / ab-hybrid 两轮运行的解读：单次运行不可作通过率结论（smk-03 跨轮不稳定）、
  smk-07/10 为系统性 G2（两模式一致）、B 在自然语言查询上无优势。
- **日期**：2026-10-24（commit 9a4a856）。
- **关键数字**：见上条；结论 = 正式 A/B 推迟到 80 条冻结集、每题 n≥3。
- **复跑**：无独立脚本（基于上述两目录 raw.jsonl 的人工分析）。

### iter1-g2fix/ — G2 修复回归第 1 版

- **是什么**：针对 smk-07/10 澄清缺失（G2）的提示词契约修复后回归（vector，smoke-10）。
- **运行日期**：2026-10-24T14:20 UTC。
- **关键数字**：8/9 通过；G\* 残留 1 题（smk-02，规则 7 收紧误伤），占位 smk-05。
- **复跑**：同 run_eval 命令（`--name iter1-g2fix`；提示词需回退到当时版本，见 docs/optimization-log.md 迭代 1）。

### iter2-v21/ — 契约 v2.1 回归

- **是什么**：规则 7 加"反向豁免"（前提已能确定时不得追问）后的回归（vector，smoke-10）。
- **运行日期**：2026-10-24T14:24 UTC。
- **关键数字**：9/9 全过（smk-02 恢复，smk-03/07/10 保持通过），占位 smk-05。
- **复跑**：同 run_eval 命令（`--name iter2-v21`，提示词契约 v2.1）。

### formal-ab/ — 正式 A/B（冻结主集 80 条，6 轮）

- **是什么**：vector 与 hybrid 各 3 轮 × 80 题（每题 n=3），冻结集正式结论的原始记录；
  汇总报告 `formal-ab/report.md` 由 `compare_formal_ab.py` 聚合生成。
- **运行日期**：2026-10-25 06:52~08:33 UTC（vector r1→hybrid r3）。
- **关键数字**（抄自 formal-ab/report.md）：
  - 每轮通过：vector 71/70/71，hybrid 69/69/69；
  - 留出集（freeze 40）headline：Evidence Recall@5（锚点级）A **81.0%**（51/63）vs B 74.6%（47/63）；
    稳定通过率 A **92.5%**（37/40）vs B 82.5%（33/40）；dev 稳定通过 A 34/40、B 36/40；
  - 不稳定题：vector 8 题（m14/15/36/42/57/59/60/74），hybrid 4 题（m38/47/59/74）；
  - 结论：**A 胜出**，混合检索在本语料不保留为默认模式。
- **复跑**：`ENABLE_REAL_MODEL_CALLS=1 bash evals/tools/formal_ab_driver.sh`（含 6 轮 run_eval 与聚合）

### min-score-calibration.md — A1 拒答阈值校准

- **是什么**：dev 集 40 题 × vector 3 轮 = 120 次运行的 top1 证据分数（C1）按预期状态分桶，
  加 0.30~0.50 阈值扫描，支撑拒答/警告两阈值决策。
- **日期**：2026-10-25（commit 5d251c7）。
- **关键数字**：answer n=105，top1 min 0.565 / max 0.791；clarify n=6（0.708~0.772）；
  refuse n=9（0.619~0.683）；0.30~0.50 各档 answer 误拒均为 0 → 拒答阈值 **0.45**、警告阈值 **0.62**。
  核心发现：分数阈值分不开"无答案"（0.62~0.68）与"可回答"尾部——离题归分数阈值，答非所问归生成契约。
- **复算说明**：2026-10-25 用 `calibrate_min_score.py`（本索引编写时补入 tools/）复算：
  n/min/max、clarify 与 refuse 两桶全部一致，阈值扫描与 0.45/0.62 决策不变；
  answer 桶 P25/median/P75 复算为 0.708/0.739/0.767，原报告 0.699/0.729/0.764（差 0.003~0.011，
  当时临时脚本未入库无法核对；四分位恰落在原始数据点上，与百分位方法无关，不影响任何决策）。
- **复跑**：`.venv/Scripts/python.exe evals/tools/calibrate_min_score.py`（只读库，无模型调用）

### failure-attribution.md — B1 失败题归因

- **是什么**：formal-ab 六轮中"同题同模式 ≥2/3 轮非 pass"的系统性失败的机械归因
  （金标不在 top-20 → R1；在 top-20 不在 top-5 → R2；在 top-5 → G 类），由
  `attribute_failures.py` 生成后人工复核答案摘录。
- **日期**：2026-10-25（commit a10c240）。
- **关键数字**：系统性失败 18 项 = G\* 10 + R1 3 + R2 5；G2 系统性失败 m67/m68 两模式一致；
  hybrid 特有失败 m57/m58/m19/m21（BM25+RRF 候选扰动）。
- **复跑**：`.venv/Scripts/python.exe evals/tools/attribute_failures.py`（只读 raw.jsonl，无模型调用）

### phase-b-experiments.md 与 phase-b-experiments-detail.jsonl — B2/B3 参数扫描 + 重排

- **是什么**：冻结 dev 38 题（剔除设计性不可达 m51/m52）纯检索实验：向量/Hybrid-RRF k 值扫描、
  top-k 对比、vector top-20 → bge-reranker-v2-m3 → top-5 重排；detail.jsonl 为每配置逐题
  "命中数/分母"明细（每行一个配置：`config` + `per_question`），供报告数字溯源。
- **运行日期**：2026-10-25（commit a10c240）；同日以 `param_sweep.py`（含 detail 导出）复跑校验，
  再生报告与已提交版本逐字节一致。
- **关键数字**（Recall，锚点级，分母 58）：vector@5 82.8%（48/58）、hybrid-rrf40@5 86.2%（50/58）、
  hybrid-rrf60@5 84.5%（49/58）、hybrid-rrf120@5 84.5%（49/58）、vector@8 87.9%（51/58）、
  hybrid-rrf60@8 87.9%（51/58）、rerank@5 87.9%（51/58）。读数：RRF k 不敏感；@5→@8 的增益即
  R2 类失败修复上限。
- **复跑**：`ENABLE_REAL_MODEL_CALLS=1 .venv/Scripts/python.exe evals/tools/param_sweep.py`
  （1 次批量 Embedding + 约 38 次 rerank，均为免费档；无生成调用）

## 复跑命令汇总

```bash
# 冒烟基线（stage1-baseline/，含语料首次入库）
ENABLE_REAL_MODEL_CALLS=1 .venv/Scripts/python.exe evals/tools/run_smoke_baseline.py

# 单轮评测（smoke-10 或 main-80；语料未变时加 --skip-ingest 省 Embedding）
ENABLE_REAL_MODEL_CALLS=1 .venv/Scripts/python.exe evals/tools/run_eval.py \
  --dataset evals/datasets/main-80.jsonl --mode vector --name <输出目录名> --skip-ingest

# 正式 A/B 六轮 + 聚合（formal-ab/）
ENABLE_REAL_MODEL_CALLS=1 bash evals/tools/formal_ab_driver.sh

# B2/B3 参数扫描 + 重排 + 逐题明细（phase-b-experiments.md / -detail.jsonl）
ENABLE_REAL_MODEL_CALLS=1 .venv/Scripts/python.exe evals/tools/param_sweep.py

# A1 阈值校准复算（只读 dev 库，不发模型调用）
.venv/Scripts/python.exe evals/tools/calibrate_min_score.py
```

辅助（无模型调用）：`compare_formal_ab.py`（重聚合 formal-ab → report.md）、
`attribute_failures.py`（重生成 failure-attribution.md）。

# 工作记录与交接说明（2026-10-24，ZCode/GLM 会话）

> 本文是本轮会话的完整工作记录，供项目作者以及后续任何会话（GPT/主脑/其他执行模型）接手时了解现状。阅读顺序建议：本文 → `docs/implementation-backlog.md` 修订记录 → 两份机检报告。
> 边界声明：本轮只做了文档整合、环境搭建与机器校验，**没有写应用代码、没有安装数据库、没有调用任何付费模型**。机器校验不构成 M0/M1 验收，也不替代作者人工复核。

## 1. 会话信息

- 执行者：ZCode（GLM 模型，ZCode 客户端），独立于此前的工作台会话（Model Desk / GPT 主脑）。
- 日期：2026-10-24。
- 授权：用户确认「可以开始，可以调用子代理」，对应上一轮总结建议的三步（评审采纳整合、环境搭建、机器校验）。数据库安装与模型调用未获授权，本轮也未执行。

## 2. 执行内容（按顺序）

1. **现状审查**：通读全部规划文档、本地模型评审包与 `PROVENANCE.md`；重算 PROVENANCE 清单中 10 个文件的 sha256，全部一致（文件未被改动）。阅读 `.model-desk/runs/20261021-164052-4c966c/review.json`，确认 10-21 那轮「执行模型自报 completed 但无交付物 → 主脑接管验收」的记录完整。
2. **环境探测**：uv 0.13.0 已在 PATH（10-21 审计中尚无）；winget v1.29.380 可用；Docker 客户端不存在；`wsl -l -v` 确认无任何发行版（仅有系统组件）。
3. **Python 环境**：新建 `pyproject.toml` + `.python-version`（3.12）+ `uv.lock`；`uv sync` 建立 `.venv`（uv 托管 CPython 3.12.15），当前依赖仅 pypdf 6.21.2、pytest 9.1.1（dev 组）。服务依赖（FastAPI/SQLAlchemy 等）留给 S1-T01/S1-T02 时再锁。
4. **目录改名**：`examples/public-docs/` → `examples/synthetic-docs/`（评审缺口 7）；`docs/data-plan.md`、`docs/implementation-backlog.md` 中的引用同步更新；原规划文档（2026-10-20）与评审文件中的旧路径按历史记录保留，不回溯修改。
5. **评审采纳**：`docs/review-gaps-20261021.md` 的 8 个缺口结论合并进任务清单与实施方案（逐项落点见 backlog「修订记录（2026-10-24）」）；README 新增「开发方法」一节并链接评审与 PROVENANCE。评审文件本身未改动，全部带原标注入库归档。
6. **机器校验**：两组独立校验（方法与结果见第 4 节），脚本与报告入库，可复跑。
7. **提交与清理**：本轮改动形成 2 个提交；删除已合并回 main 的旧分支 `docs/implementation-plan`、`docs/stage0-environment-data`。

## 3. 文件改动清单

| 文件 | 变更 | 说明 |
|---|---|---|
| `examples/synthetic-docs/**` | 改名（自 `examples/public-docs/`） | 内容零改动，git 以 R（rename）记录 |
| `docs/data-plan.md` | 修改 | 改名说明 + 5 处链接更新 |
| `docs/implementation-backlog.md` | 修改 | 修订记录；新增 S1-T12/S1-T13；S0-T07 增条件 6/7；S1-T10 增条件 6/7；S3-T02/S3-T07 增补；S4-T05 监控设计（原验收顺延 S4-T06）；相关依赖与总览计数同步 |
| `docs/implementation-plan.md` | 修改 | §9 增补评测有效性/口径/归因/夹具段；M4 退出条件增监控设计；§12 增 2026-10-24 状态行 |
| `README.md` | 修改 | 链接增评审与 PROVENANCE；新增「开发方法」一节 |
| `PROVENANCE.md` | 修改 | 增「2026-10-24 复核与采纳记录」（注意：本文件被修改，其原 sha256 自校验声明随之失效，属预期） |
| `docs/00-environment-audit.md` | 修改 | 增「§5 2026-10-24 增补」：uv 可用、venv 建立、Docker/WSL 现状 |
| `docs/review-gaps-20261021.md` | 新增入库 | 本地模型第三方评审（原样归档，保留标注） |
| `evals/badcase-taxonomy.md` | 新增入库 | 六类归因 + 金标核对模板（原样归档） |
| `evals/smoke-10-draft.jsonl` | 新增入库 | 10 条冒烟题草稿（原样归档，**作者人工复核未做**） |
| `examples/format-fixtures/**` | 新增入库 | 3 份格式夹具 + 生成脚本 + README（原样归档） |
| `pyproject.toml` / `.python-version` / `uv.lock` / `.venv/` | 新增（venv 已忽略） | 项目 Python 环境与锁定 |
| `evals/tools/verify_gold_anchors.py` | 新增 | 冒烟题锚点机检脚本（纯标准库，可复跑） |
| `evals/anchor-check-20261024.md` | 新增 | 锚点机检报告 |
| `evals/tools/check_fixtures.py` | 新增 | 夹具声明复核脚本（pypdf + 标准库） |
| `evals/fixture-check-20261024.md` | 新增 | 夹具复核报告 |
| `docs/worklog-20261024-zcode.md` | 新增 | 本文 |

## 4. 机器校验结果摘要

### 4.1 冒烟题锚点（`evals/anchor-check-20261024.md`，子代理执行）

- 10 条题、15 处 gold 证据：`version_id` 15/15 有效、条款锚点全部命中、`text` 摘录全部与原文**精确一致**（归一化后 exact，无改写）。
- smk-09 日期独立验算（datetime，独立于题面）：2026-10-16 为周五；次一工作日起 3 个工作日 = 10-19/10-20/10-21，截止 10-21 18:00；与 A-F-02 交叉核对全过。
- 干扰源抽查成立：「5 个工作日」在 v1 A-D1-02、「7 个自然日」在 kb-b B-D1-01。
- **作者需人工确认的 6 个复核点**（机器不改草稿，详见报告）：
  1. smk-09 的 `must_not_include` 含「10-19」，与 `required_info_points`「10-19 为第 1 日」字面冲突（疑本意为“不得把 10-19 当截止日”）；
  2. smk-02 的 `must_not_include`「3 个自然日」不在语料中（疑应为「7 个自然日」或注明为幻觉护栏）；
  3. smk-05 的「7 自然日」应写为语料原形「7 个自然日」；type「权限」的计分口径未定义；
  4. smk-03 的 type「版本回溯」的计分口径未定义；
  5. smk-04「另设整改完成天数」在 A-R-02 以否定形式出现，评分器需防误伤；
  6. 全部 10 条按 `evals/badcase-taxonomy.md` 第 3 节人工确认并留痕（`reviewed_by: author`）。

### 4.2 格式夹具（`evals/fixture-check-20261024.md`，子代理失败后由主会话执行）

- 53 项断言全部通过：跨页表格（L1–L18 第 1 页 / L19–L30 第 2 页，表头逐页重复）、页眉页脚逐页污染、扫描样 PDF 0 可抽取字符 + 1 张 JPEG 图、脏 TXT 的 BOM/全角/`\r\r\n` 切断条款号、DOCX/PDF 来源元数据、sha256 前缀。
- 唯一实质发现：PROVENANCE 称 PDF `/Title` `/Subject`「已写入来源信息」，实测为描述性内容（`fixture-table` / `synthetic format fixture`），不含来源标注；是否修订措辞由作者定（修订会使 PROVENANCE 哈希变化，需同步更新清单）。
- 过程记录：执行该任务的子代理因并发上限失败，遗留脚本由主会话接手修正（初版正则两处误判：去空白文本导致 L30 漏配、`\r\n` 与实际 `\r\r\n` 不符），修正后全过。脚本保留作为 S1-T13 断言的参考实现。

## 5. 未做 / 未验证（诚实边界）

- 未安装 Docker / PostgreSQL / pgvector；未创建任何数据库。
- 未调用任何 Chat/Embedding 模型（包括本地模型）；未下载模型。
- 未写任何应用代码（S1-T01 及以后均未开始）。
- `smoke-10-draft.jsonl` 的作者人工复核未做；机检报告不能替代它。
- 两份机检报告只覆盖「锚点与原文一致性」「夹具声明真实性」，不是评测集冻结，也不是 M0 退出验收。

## 6. 待项目作者决策

1. **模型来源与费用边界**（S0-T04/S0-T06，阻塞真实链路）：产品生成模型与 Embedding 各用什么提供方？最小连通验证的调用规模与费用上限？没有这个授权，S1-T05 之后只能用 mock。
2. **数据库路线**（本机探测结果：无 Docker、WSL 无发行版、winget 可用）：
   - A（建议）：安装 Docker Desktop（需先启用 WSL2 发行版、管理员权限、可能重启），用官方 `pgvector/pgvector` 镜像 + `docker-compose.yml`，最贴合实施方案的部署设计；
   - B：winget 安装原生 Windows PostgreSQL——pgvector 无官方 Windows 预编译包，需 MSVC 自行编译，不推荐；
   - C：远程实例（如带 pgvector 的云免费档）——零本地安装，但涉及数据出境与账号费用，由作者认可。
3. **PROVENANCE 措辞**：`/Title` `/Subject` 的出入是否修订（见 4.2）。
4. **冒烟题 6 个复核点**（见 4.1）确认后，把 `smoke-10-draft.jsonl` 升级为正式冒烟集并填 `evals/gold-review.md`。

## 7. 给下一个会话的起点

建议执行顺序（依据 backlog 依赖）：

1. S0-T04 模型与费用方案（需作者输入）；拿到授权后 S0-T06 最小连通。
2. 可离线并行：S1-T01 仓库骨架 → S1-T02 数据模型与迁移（不可变版本、发布指针、任务唯一约束）；S1-T12 语料扩充（150～250 条款、≥30% 近邻干扰，评审缺口 1）；S1-T13 夹具 fail-loud 断言（可参考 `evals/tools/check_fixtures.py`）。
3. 复跑本轮校验：

```bash
cd /e/AIjob/gpt/rag
.venv/Scripts/python.exe evals/tools/verify_gold_anchors.py   # 冒烟题锚点
.venv/Scripts/python.exe evals/tools/check_fixtures.py        # 夹具声明（退出码 0 = 全过）
```

## 8. 本机环境快照（2026-10-24）

| 项 | 状态 |
|---|---|
| Git | 2.56.0.windows.2，main，本轮后基线见 `git log` |
| uv | 0.13.0（`C:\Users\lu150\.local\bin\uv.exe`） |
| 项目 Python | `.venv` = uv 托管 CPython 3.12.15；pypdf 6.21.2、pytest 9.1.1 |
| Node | v22.23.3（`E:\pi\node\node\node.exe`，非项目安装，未锁版本） |
| Docker / PostgreSQL | 均不可用；WSL 无发行版 |
| winget | v1.29.380 可用（可用于后续安装 Docker Desktop 等，需管理员） |
| 端口 3000/8000/5432 | 本轮未复查（沿用 10-21 无监听快照，启动前应重查） |

---

## 9. 同日第二轮：模型接入与数据库路线（用户已决策）

用户在本轮总结后拍板：(1) 生成模型用其本地自部署端点（无密钥），能力不足再提供 DeepSeek 密钥；询问 Embedding 是什么（已解答：语义向量编码模型，与聊天模型相互独立）；(2) 数据库路线采纳建议（Docker Desktop + 官方 pgvector 镜像）。

### 9.1 已执行

- **生成模型连通（S0-T06 生成半项通过）**：`/v1/models` 返回唯一模型 `qwen3.8-flash-next-iq3_xxs`（`n_ctx=262144`，输入 text+image）；中文问答 1 次准确且守指令；严格 JSON 引用契约 1 次通过（可解析、只引 C1、答案正确）。费用记「自有硬件，无 API 账单」。注意：Git Bash 直接 curl 中文会按 GBK 发送导致服务端解码报错，探测须用显式 UTF-8 的 HTTP 客户端。
- **Embedding 未通过**：该端点 `POST /v1/embeddings` 实测 404；DeepSeek 官方 API 亦无 Embedding 接口。选项与建议（本地部署 bge-m3 为建议项，云端 API 为备选）写入 `docs/model-and-cost.md` §2，待用户部署/选定。
- **S0-T04 初版交付**：`docs/model-and-cost.md`（生成已确认、Embedding 待定、费用规则、`.env` 变量约定）、`.env.example`、本机 `.env`（真实值，已确认被 gitignore 排除）。
- **数据库路线落地物**：`docker-compose.yml`（仅 `pgvector/pgvector:pg16` 数据库服务 + healthcheck，应用服务留给 S1-T01）；Docker Desktop 经 winget 启动安装（结果见 9.2）。
- **文档状态同步**：backlog S0-T04/S0-T06 状态与 §10、plan §8 各增补一段。

### 9.2 进行中 / 待办

- Docker Desktop 安装（winget 后台执行）。装完仍需：首次启动接受条款、确认 WSL2 后端（本机 WSL 无发行版，Docker Desktop 自带两个发行版即可，无需额外安装）、`docker compose up -d` 起 pgvector 并跑 `CREATE EXTENSION vector` 冒烟。若安装因管理员权限/重启受阻，交接时如实记录剩余手工步骤。
- Embedding 选型：用户部署本地 bge-m3 或选云端 API → 回填 `model-and-cost.md` → 补 S0-T06 Embedding 半项 → 解锁 S1-T05。
- 下一步开发（离线可做）：S1-T01 骨架 → S1-T02 数据模型迁移；S1-T12 语料扩充；S1-T13 夹具断言。

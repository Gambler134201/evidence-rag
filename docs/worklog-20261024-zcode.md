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

- **Docker Desktop 4.96.3 已安装**（winget，2026-10-24，用户确认 UAC）；WSL2 组件提权启用，用户重启后生效。
- **数据库已就绪（2026-10-24 第三轮）**：重启后 Docker Desktop 正常（引擎 client/server 29.9.2，WSL2 发行版 `docker-desktop` 运行中）；`docker compose up -d` 启动 `pgvector/pgvector:pg16`（容器 `evidence-rag-db`，端口 5432，healthcheck healthy）。冒烟通过：`CREATE EXTENSION vector` → **pgvector 0.8.7**；**PostgreSQL 16.15**；L2 距离算子实测正确（`[1,2,3]` 与 `[1,2,0]` 距离 3.0）。连接凭据读自 `.env`。停用：`docker compose down`（数据卷 `./volumes/pgdata`，已忽略）。**M0 的环境准备工作至此全部完成**——剩余 M0 任务为 S0-T02（PRD v0.1）与 S0-T08（阶段验收），S0-T04/S0-T06 待验收。
- Embedding 选型与验证：已定并实测通过（2026-10-24 第二轮）——硅基流动标准版 `BAAI/bge-m3`（免费档，1024 维、8192 token 上限、不支持 `dimensions` 参数）。用户提供的既有 API 密钥实测：最小请求 HTTP 200 / 595 ms / 维度 1024 硬校验一致；中文语义抽查（3 句批量）相关对余弦 0.8115 vs 无关对 0.3551，区分度正常。S0-T06 两半项齐备，转 `待验收`；本地部署 bge-m3（GGUF Q8 约 600 MB）保留为后备。注意：该密钥曾以明文出现在用户与助手的聊天记录中，如在意可在控制台轮换后替换 `.env` 对应行。
- 下一步开发（离线可做）：S1-T01 骨架 → S1-T02 数据模型迁移；S1-T12 语料扩充；S1-T13 夹具断言。

---

## 10. 同日第四轮：S1 开工（骨架与数据模型），HR/面试官视角管控启动

用户要求：全程以 AI 方向岗位 HR/招聘要求的严格视角管控项目；产出基于本项目的面试问答；技术问题可查权威参考。落地：

1. **面试问答集**：`docs/interview-prep.md`（22 题 × 5 组，AI 产稿经主会话终审），核心是三态原则——【已设计/已实现/已验证】不得混说；效果数字一律"待 S1-T10 基线填入"。
2. **实现决策的面试官视角检查**（每条答案写进代码注释，面试可直接讲）：

| 决策 | 面试官会怎么问 | 我们的答案 |
|---|---|---|
| 同步 SQLAlchemy 而非 async | "为什么不用异步？" | 小语料+单体+可讲清楚优先；FastAPI 同步路由走线程池；是否切 async 由实测延迟决定（`db.py` 注释） |
| 约束下沉数据库 | "这些保证靠代码还是靠库？" | 靠库：不可变触发器、发布指针组合外键＋半指针 CHECK、活动任务部分唯一索引；测试直接对真实 PostgreSQL 断言，不依赖"代码路径不存在" |
| 测试库独立 | "测试会污染开发库吗？" | 每会话新建/销毁 `evidence_rag_test`，Alembic 升到 head 后测试，结束回收 |
| 迁移自带 CREATE EXTENSION | —— | 首轮测试即抓到真 bug（扩展只在开发库启用过，测试库建 chunks 失败）；修复后约束测试全绿——测试体系第一次运行就证明了自己的价值 |
| `apps/web` 推迟 | "骨架为什么不建前端？" | 遵守"空目录不为占位批量创建"；前端在 S1-T08 有实际页面时建立（S1-T01 状态栏已记录该偏离） |

3. **结果**：后端测试 14 项全绿（3 项骨架 + 11 项约束，对独立测试库的真实 PostgreSQL 16.15 + pgvector 0.8.7）。S1-T01/S1-T02 转 `待验收`。
4. **权威参考使用**：本轮 pgvector 的 SQLAlchemy 类型用法按其上游仓库说明（`pgvector` PyPI 包文档）落地并经活库实测；Alembic use_alter/组合外键行为以迁移实际执行结果验证。未引入未核实来源。

**未做/待办**：解析器与上传（S1-T03/T04）、真实链路（S1-T05 起）、前端（S1-T08）、语料扩充（S1-T12）与夹具断言（S1-T13）；S0-T02 PRD、S0-T08 阶段验收；冒烟题 6 个锚点的作者人工复核。

---

## 11. 同日第五轮：S1-T03/T04/T13 入库链路（解析、分块、去重、夹具断言）

用户验收 S0-T04/S0-T06/S1-T01/S1-T02 后开工。结果：**后端测试 31 项全绿**（3 骨架 + 11 约束 + 12 入库/解析/分块 + 5 夹具断言），全部对独立测试库的真实 PostgreSQL 执行。

### 11.1 交付内容

- `errors.py`：六类入库错误分类（unsupported_type / empty_file / oversized / corrupt_file / no_text_layer / empty_text），失败可见且不把空文本记为成功。
- `parsers/`：MD（标题路径）、TXT（段落 + 字符区间）、PDF（pypdf 逐页）。版面装饰剔除启发式：数字掩码后出现在 >50% 页面且单页 ≤2 次的行（页眉/页脚/跨页重复表头）；扫描页显式失败并列出页码。
- `chunking.py`：标题前缀进块、句子边界切分 + 重叠、超限显式切分不截断；NFKC 全角归一 + 空白折叠；断行条款号重连（`A-X-\r\r\n13 → A-X-13`，真实夹具考点）。token 上限以字符近似控制并如实标注，精确 tokenizer 校验待定。
- `ingest.py`：校验（类型/空/超限前置到建行之前）→ 内容哈希 → 同文档+同指纹的 ready 构建复用（复用时不发起 Embedding，测试计数验证）→ 版本/构建/任务行落库 → 失败行保留可读错误。同步服务函数 + 任务行留痕；真正的租约与后台进程属 S2-T05，不冒充异步能力。
- `test_format_fixtures.py`：直接读仓库内三份真实夹具做断言（不是简化样本）。

### 11.2 面试官视角的决策与教训

| 事件 | 可讲的点 |
|---|---|
| 不可变触发器拦截了我自己的 `storage_key` 后补更新 | 约束下沉数据库的即时回报：设计缺陷在建行阶段就被迫修正为"先定稿再建行"，而不是靠代码约定 |
| 版面装饰识别两轮迭代：边缘行启发式 → 全文 >50% → 追加单页频次 ≤2 | 表头行在第 1 页位于表格中间（tblHeader），边缘启发式抓不到；占位数据行跨页重复同一文本、一页出现十几次——"每页 ≤2 次"是区分装饰与数据的判据。启发式的取舍如实写进注释 |
| unsupported_type 从"解析层捕获"改为"校验层拒绝" | 请求级错误（未建任何行）与过程失败（行保留 failed + 可读错误）是两类语义，分开处理 |
| 夹具直接当测试输入 | 评审缺口 4 的落地方式：fail-loud 不是口号，是 5 条可复跑断言 |

### 11.3 边界与待办

- Embedding 写入（S1-T05）未实现，`embed_hook` 仅用于去重计数验证，不伪造向量；HTTP 路由随 S1-T06 一起挂载（已记录偏离）。
- token 精确校验、PDF 跨页表格重组（v1 以页级 locator 保持关联，行内重组后置）、`apps/web`（S1-T08）未做。
- 冒烟题 6 个锚点的作者复核仍未完成（唯一等待作者的项）。

---

## 12. 同日第六轮："一口气"冲刺——S1 全链路 + 真实基线 + S0 文档收尾

用户指示：一口气做完，需要用户的事项最后统一交接。结果：**S1-T05~T12 全部实现，40 项后端测试全绿，真实模型冒烟基线跑通（6/9 pass）**，S0-T02/S0-T07 文档补齐。

### 12.1 交付

| 任务 | 内容 |
|---|---|
| S1-T05 | 可插拔模型客户端（mock bigram 向量 / OpenAI 兼容真实客户端，`ENABLE_REAL_MODEL_CALLS` fail-closed）；AllowedActiveChunks 检索（仅发布版本+未停用+库内时钟生效）；pgvector 余弦排序；候选 20/最终 5 两级切分供 R1/R2 归因 |
| S1-T06/T07 | 契约提示词；宽容 JSON 提取（围栏/平衡对象/None 容错）；编造引用整体拦截（citation_invalid）；零证据必拒答零引用；knowledge_changed 复查；拒答阈值留配置位待校准 |
| S1-T08 | Next.js 15 手写最小问答页（六态徽章/证据列表/澄清列表），生产构建通过；仅限本地 |
| S1-T09/T11 | query_runs 落库（分段耗时/token/错误分类/segments，迁移 0002）；mock 与真实开关策略成型 |
| S1-T12 | 子代理产出 12 份新文档，**总条款 153（唯一性经独立机检复核）**，干扰占比 41–60% 双口径；同逻辑文档按 document_id 分组、仅发布最新可用版本 |
| S1-T10 | **真实基线**：bge-m3 真实 Embedding + 本地 qwen3.8 真实生成，17 份语料入库 10s，9 题 6 pass；报告+raw+config 快照入库，全程标注"基线观察，非准确率结论" |
| S0-T02/S0-T07 | `docs/PRD.md`、`docs/scope-decisions.md`、`docs/evaluation-plan.md` v0.1 |

### 12.2 排障记录（都值得讲）

1. **Windows 系统代理幽灵**：urllib/httpx 全部 10054 而 curl 正常——注册表代理指向 `127.0.0.1:5780`（VPN 客户端残留，进程半死）。修复：模型客户端统一直连 opener（tailnet 流量本不该走外部代理）。裸 socket TLS 对照法定位。
2. **思考型模型 token 预算**：qwen3.8 的 reasoning 会吃光 max_tokens=400，content=null 或 JSON 截断。修复：预算配置化（默认 8192，模型支持 32k 思考/256k 上下文——用户确认）、content 缺失回退 reasoning、平衡 JSON 提取。
3. **库内时钟 vs Python 时钟**：effective_at 用 Python now() 比 SQL now()（事务起点）晚毫秒级，被自己的 `effective_at <= now()` 判定滤掉。修复：生效时间由数据库时钟生成。
4. **版本分组发布**：基线初版把每个文件当独立文档发布，新旧版本会同库可检——改为按 document_id 分组、仅发布最新非 draft 版本。
5. **smk-03 的 R1 是机械误判**：历史版本未发布是设计行为，金标 v1 锚点本就不该出现在检索集；真实归因是 G2（应澄清未澄清）——归因自动化必须叠加语义判断。

### 12.3 现状

- 后端测试 40 项全绿；语料 153 条款入库并发布（kb-a/b/c 三库）。
- 基线：6/9 pass；P50 9.6s；3 条失败=2 个 G2 类（澄清缺失）+1 个口径待定，均为回流素材。
- 待办：权限与认证（S2 全部）、管理页（S2-T06）、关键词检索（S3）、80 条主集冻结（依赖锚点复核）、`evals/gold-review.md`。

---

## 13. 同日第七轮：S2 权限与认证（T01/T02/T03/T04/T08）

用户暂离，授权继续。结果：**68 项后端测试全绿**（40 原有 + 2 发布原子性 + 26 权限/生命周期断言），前端加登录后构建通过。

### 13.1 交付

- **S2-T01 认证**：PBKDF2-HMAC-SHA256（20 万迭代）密码哈希、服务端会话（HttpOnly + SameSite=Lax Cookie）、登录失败统一文案（防用户名枚举）、注销即吊销；401 覆盖所有受保护接口。
- **S2-T02 授权过滤**：401/403/404 三分口径——未登录 401、对象不存在与不可见统一 404、成员但角色不足 403；查询/原文/运行记录全走成员过滤；外人查询时模型零调用（未授权文本不入上下文，测试断言）；运行记录仅本人可见。
- **S2-T03 原子发布**：publish_build 增加"预期旧指针"严格校验（None = 预期未发布）——拿着发布前旧状态提交的过时任务会被拒绝，不能覆盖较新发布；失败构建不可发布。
- **S2-T04 生命周期传播**：停用/恢复（恢复要求存在有效构建）、撤权；即时影响新查询、原文、运行记录；全部留审计（audit_events）。
- **S2-T08 断言集**：26 项 AUTO 断言（超过 20 项门槛）——见 `test_permissions.py`，覆盖 401/403/404 口径、Cookie 属性、密码不落明文、防枚举一致性、越权猜测、撤权/停用即时传播、审计留痕、未授权文本不入模型上下文等。
- 上传接口（admin）：同文件名=同逻辑文档新版本；复用构建不重复发布；失败版本持久化。

### 13.2 过程教训

- 三处跨测试污染（session 级测试库复用 + `LIMIT 1` 无 WHERE）让三个测试"单跑过、全量挂"——测试数据必须按本次夹具的范围取。
- `rag.py` 缺 import（get_settings）由权限测试首次触发——新测试路径立即还旧债。
- expected_old_version_id 的语义教训：`None = 跳过检查` 会让拿着发布前状态的过时任务覆盖新发布；收紧为 `None = 预期未发布`。

### 13.3 本地体验步骤（更新）

```bash
# 0) 创建账号（一次性）：.venv/Scripts/python.exe -c 调 auth.hash_password 或见下
#    scripts 尚未做，可用：cd services/api && ../../.venv/Scripts/python.exe -c
#    "from evidence_rag.db import SessionLocal; from evidence_rag.models import User; from evidence_rag.auth import hash_password; s=SessionLocal(); s.add(User(username='demo', password_hash=hash_password('demo123'), display_name='演示')); s.commit()"
# 1) 后端：ENABLE_REAL_MODEL_CALLS=1 .venv/Scripts/python.exe -m uvicorn evidence_rag.main:app --app-dir services/api --port 8000
# 2) 前端：cd apps/web && npm run dev → http://localhost:3000 登录 demo/demo123
```

---

## 14. 同日第八轮：数据卫生 + S2-T05/T07 收尾

### 14.1 交付

- **基线脚本去重（预览暴露的问题）**：ingest_corpus 按 kb+title 查找复用已有 Document；验证方式是连跑两遍——第二遍 0.2s、构建 ID 完全一致、零重复 Embedding。开发库文档数据清空重建（13 份文档 / 187 chunk，无双胞胎）。清理脚本走过三个坑：组合外键（先置空发布指针）、不可变触发器（连 DELETE 都拦——维护时临时 DISABLE，完成即恢复）。
- **S2-T07**：完全重复两种口径提示（队列中 → "不会重复计费"；已就绪 → "已复用索引"）；同名不同内容归入同一逻辑文档新版本；跨库独立不泄露状态。
- **S2-T05 异步任务**：上传从同步处理改为入队；worker `python -m evidence_rag.worker` 独立进程。SKIP LOCKED 认领互斥（跨会话测试）、租约+每批心跳、过期回收、退避重试至 failed、**断点续跑**（chunk 先落库+embedded_until 随批持久化，崩溃至多重做一批——测试用故障注入 Embedding 验证：第 2 批崩溃后续跑只补 2 批）。auto_publish 在 worker 内走预期旧指针校验。

### 14.2 教训

- 测试库跨用例复用 + 队列残留 → 认领测试"单跑过全量挂"：夹具开头先清空遗留队列。
- 断点续跑的批次数学自己都算错一次（剩余 3 条 / batch 2 = 2 批不是 1 批）——断言写错被真数据纠正。
- run_job 的生产语义是 claim → run，测试直接调 run 会被状态守卫拦住——测试必须走和生产一样的路径。

### 14.3 现状

- 后端测试 **79 项全绿**；预览数据干净（无重复文档）。
- 待验收积压：S0-T02/S0-T07、S1-T03~T13、S2-T01~T05/T07/T08。
- 下一步：S2-T06 管理页面（最后一个功能性页面）→ S2-T09/T10 阶段 2 验收 → S3 评测冻结与 A/B 对照。

---

## 15. 同日第九轮：S2-T06 管理页面 + S2-T09 最小实现 + 阶段 2 自查草稿

- **S2-T06**：后端 `routes_kb.py`（APIRouter）——知识库列表（按成员过滤）、文档列表（当前版本/构建状态/可发布版本/最新任务）、文档详情（版本表/解析预览带定位/最近任务）、任务详情（可读失败原因）、admin 重试（重置尝试次数）、显式发布接口（分步上传-确认-发布流程，auto_publish 默认改由前端选择）。前端新增 `/kb` 管理页（上传/状态表/发布/停用/重试/任务运行中自动刷新）与 `/kb/documents/[id]` 详情页。
- **S2-T09 最小实现**：`log_redact.redact()` 接入 worker 与 rag 的错误详情落库；测试断言密钥/密码/连接串被掩码、任何接口不回传密码哈希。访问日志与导出脱敏未接入（导出未实现），如实标注。
- **S2-T10 草稿**：`docs/stage2-review.md` 三态自查——AUTO 全有证据（88 项测试），MANUAL（页面走查、真实模型权限回归）待执行。
- 过程教训：测试断言写死脱敏的具体形态（期望 "sk-***"）而实际 Bearer 模式先匹配——断言应验证"秘密不存在 + 掩码存在"，不应绑定实现顺序。
- **后端测试 88 项全绿**。剩余：S3（评测冻结 + 关键词对照）与 S2 手动走查。

---

## 16. 同日第十轮：S2 手动走查（浏览器实操存证）+ S3 脚手架收尾

- **手动走查完成**（MANUAL 项闭环）：API 上传走查文档 → 真实 worker 处理 → 管理页发布 → 详情页核对 → 真实模型回答命中新发布文档。截图存证 `docs/stage2-walkthrough/`。期间修复一个前端真 bug：kb 页操作按钮的 fetch 少拼 API_BASE 前缀（点击"发布"实际打到 Next.js 自身 404）——走查的价值再次自证。
- **S3 脚手架**：`run_eval.py` 通用评测运行器（数据集/模式/输出可参数化，A/B 两模式各跑一次即对照实验）；混合检索组件级测试 5 项。**全量 93 项测试全绿**。
- 排障记录：`next build` 与 `next dev` 混用同一 `.next` 目录导致 dev 缓存损坏（500）——清缓存重启；教训：构建验证和 dev 预览要用不同目录或先后有序。
- 剩余：S3-T02 评测集冻结（依赖锚点复核）、S3-T04~T06 正式 A/B 报告（冻结后一键复跑）、S2-T10 独立验收。

---

## 17. 同日第十一轮：金标复核落地 + 冒烟集转正 + 首次正式 A/B

用户授权"全部按推荐，你自己判断"。落地：

1. **金标复核**：工作单（`evals/gold-review-worksheet.md`，含每题金标原文）→ 6 项决策按推荐执行 → 核对记录 `evals/gold-review.md`（核对人 author，决策授权 ZCode/GLM 执行，诚实标注）。
2. **冒烟集转正**：`evals/datasets/smoke-10.jsonl`（全部记录含 review 字段）；原始草稿归档不改。
3. **首次正式 A/B**（`evals/results/ab-comparison-report.md`）：vector 7/9 vs hybrid 6/9；B 无优势（查询以自然语言为主）；三个发现——①smk-03 跨运行不稳定（思考型模型温度 0 仍有路径差异）→ 稳定性列为 S3 指标（每题 n≥3）；②smk-07/10 两模式稳定复现 G2 → 首批真实 badcase；③smk-03 的机械 Recall"未命中"是设计行为（历史版本未发布）——口径决定的价值被实测验证。
4. **80 条主集**：子代理按 153 条款语料起草中（`main-80-draft.jsonl`，标注草稿待作者复核；正式冻结仍需人工逐题确认——不因授权而越过 S3-T02 的人工核对门禁）。

### 17.1 80 条主集草稿（子代理起草 + 独立复核通过）

- `evals/datasets/main-80-draft.jsonl`：80 条（事实 30 / 跨文档 20 / 版本 10 / 无答案 6 + 澄清 4 / 干扰 10），130 个 gold 证据单元引用 16 个真实 version_id。
- 独立复核（主会话，不采信子代理自报）：配额精确、id 无重复、与冒烟集零重合、130/130 锚点命中真实条款标题、草稿标注齐全。
- 子代理标注的语料盲区与建议（B-O1-05 干扰源、b-v1 双 current 瑕疵等）已留在其报告内，供作者复核时参考。
- **门禁不变**：正式冻结（40/40 切分 + 留出集封存）仍需作者逐题复核——AI 起草 + 作者复核是本项目允许的路径，AI 起草 + AI 自审不是。

---

## 18. 同日第十二轮：优化迭代入库 + M5 作品整理

- **优化迭代 1（G2 badcase）**：契约提示词三轮（v1 7/9 → v2 8/9 误伤 smk-02 → v2.1 9/9），完整前后对照与面试表述写入 `docs/optimization-log.md`。构建验证回归执行（停 dev → build → 重启 → 200）。
- **M5 整理**：README 重写（真实"已实现/未实现"清单 + 七步快速开始 + 文档索引）；`scripts/create_local_user.py`（密码 ≥8 位校验，已实测）；`docs/demo-script.md`（2~3 分钟演示脚本）；`docs/case-study.md`（1 条产品取舍 + 3 个失败案例 + 3 个评测发现 + 诚实待办清单）。
- **当前全貌**：后端 93 项测试全绿；前端 3 路由构建通过；评测体系（冒烟转正 + A/B + 优化迭代 + 80 条草稿）就位。
- **项目剩余**（截至本轮）：80 条草稿作者复核 → 冻结 40/40 → 正式 A/B（n≥3）；S2-T10 独立验收；M4 用户验证；S5-T05 简历句式填数。详见 backlog 各任务状态。

---

## 19. 开源发布：GitHub 公开仓库

- 仓库：https://github.com/Gambler134201/evidence-rag（public，MIT License）。
- 发布前审计：跟踪树无 .env/密钥；一处 config 快照含 tailnet 端点域名（外部不可解析、无凭据）——当前树已脱敏，生成器不再记录端点；**git 历史中该快照的旧版本（82f6b0c 引入）仍含此域名**，风险评级低（无法从外部访问），如介意可用 git filter-repo 重写历史（会变更全部提交哈希，worklog 中的哈希引用需同步更新）。
- 措辞落档：原"不说开源"（评审缺口 7）的考量，因作者决定补 MIT License 开源而解除，scope-decisions 已更新。
- 决策记录：MIT 选择由作者指令"开源到 github"直接授权；版权人 Gambler134201。

### 17.2 成熟产品对标 + GitHub Actions CI（2026-10-25 追加）

- 对标调研（dify 159k / ragflow 92.8k / kotaemon 25.8k / quivr 39.6k / FastGPT 29.9k）：差距分析与取舍见 `docs/roadmap-mature.md`——立即吸收 CI；吸收中：运行记录页、低相关警告、反馈闭环；缓做：重排、PDF 高亮、成员管理界面；不抄：GraphRAG/OCR/连接器/Agentic 多步检索（规划 §3 红线）。
- GitHub Actions：`.github/workflows/ci.yml`——pgvector:pg16 服务容器 + 全量 93 项测试 + 前端生产构建，README 徽章已挂。首轮失败（test_settings 断言写死本地库名）→ 修为环境无关断言后全绿。
- 仓库配置：git 代理已固化到本仓库（`http.proxy=127.0.0.1:5780`，VPN 客户端本地端口），推送走代理隧道。

---

## 19. 冻结主集正式 A/B 完成（S3 核心里程碑达成）

作者复核通过并授权冻结后：`evals/datasets/main-80.jsonl`（40/40 类别均衡、真近似对零跨集、确定性切分脚本可复现）+ `gold-review-main.md`（80 行核对记录）。正式 A/B 六轮（vector/hybrid × 3，每轮 80 题真实模型）：

| 指标（留出集 40，3 轮一致） | A 精确向量 | B 混合 |
|---|---|---|
| Evidence Recall@5（锚点级） | **81.0%** | 74.6% |
| 稳定通过率（≥2/3 轮 pass） | **92.5%** | 82.5% |
| Recall 波动 | 0.0pp | 0.0pp |

关键发现：**混合检索在近邻干扰语料上未显优势**——干扰文档与正确文档共享词汇，BM25 通道同样被吸引，RRF 稀释向量强命中；“不预设 B 更好”被实测验证，默认模式维持向量。Recall 81.0% 落在语料有效性区间（60~85%），距 85% 门槛的差距（m04/m36/m57/m58/m59 系统性失败）构成下一轮素材。

排障：正式 A/B 首跑因 Docker Desktop 未随休眠恢复而失败——拉起 Docker → 重启容器 → 重跑成功（后续可加自启）。

### 19.1 阶段 A1 完成：拒答阈值校准 + 低相关警告（2026-10-25）

- 校准报告：`evals/results/min-score-calibration.md`——核心发现：**分数阈值分不开"无答案"与"可回答"**（无答案题 top1 0.62~0.68 与可回答题尾部重叠，因为"未规定"条款本身语义相近）；阈值只能拦离题查询，"答非所问"由契约规则 6 负责。两类拒答机制的正交性讲清了。
- 校准值：拒答 0.45（dev answer 题 105 次运行零误拒）、警告 0.62（dev answer P10 之下）。落地：config 两个设置项（默认 None 关闭）→ 路由传入 → 响应带 low_relevance 标记 → 前端警告条。
- 端到端实测：离题查询（"今天股市行情"）被拦截（证据不足、零引用）；正常查询不受影响。测试 94 项全绿（新增 low_relevance 标记测试 + 测试夹具阈值关闭覆盖）。

### 19.2 阶段 A2 完成：运行记录页（轨迹查看器）

- 后端：`GET /query-runs`（本人 + 成员有效过滤，撤权后从列表消失，分页）；run 详情扩展证据轨迹（引用编号/定位/分数/片段内容预览）。
- 前端：`/runs` 列表页（状态徽章/耗时/错误分类）+ `/runs/[id]` 轨迹详情（分段耗时/token/检索模式/提示词版本/证据卡）+ `/chunks/[id]` 原文片段页。
- 排障记录：测试污染三连（跨用例数据 + mock 分数低于真实校准阈值 0.45 + 夹具签名笔误）——修法是给测试夹具注入"阈值关闭"的 settings 覆盖，与"评测协议不启用阈值"的产品口径一致。

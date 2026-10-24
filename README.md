# 知据 / evidence-rag

面向小型团队的可溯源知识助手：从**有效且有权限**的文档中回答问题，每个结论都带可核对的原文引用；证据不足时明确拒答或追问，绝不编造。

当前状态：**阶段 2（权限与版本管理）代码完成并通过 93 项自动化测试；阶段 3（评测对照）脚手架就绪**。核心闭环已可用：登录 → 多知识库管理 → 上传/异步处理/发布/停用 → 授权检索（向量/混合两种模式）→ 契约化回答（六态）→ 引用溯源 → 运行记录。

## 快速开始

前置：Docker Desktop（含 WSL2）、[uv](https://docs.astral.sh/uv/)、Node.js ≥ 18，以及一个 OpenAI 兼容的生成模型端点（本项目用本地自部署模型）和一个 Embedding 服务（本项目用硅基流动 `BAAI/bge-m3` 免费档）。

```bash
# 1) 数据库（PostgreSQL 16 + pgvector）
docker compose up -d

# 2) 依赖
uv sync

# 3) 配置：复制 .env.example 为 .env，填入生成端点与 Embedding 密钥
#    （GENERATION_BASE_URL / GENERATION_MODEL / EMBEDDING_API_KEY 等）

# 4) 建表
cd services/api && ../../.venv/Scripts/python.exe -m alembic upgrade head && cd ../..

# 5) 创建演示账号（三库管理员）
.venv/Scripts/python.exe scripts/create_local_user.py demo demo12345 --admin-all

# 6) 起三个服务（各开一个终端）
ENABLE_REAL_MODEL_CALLS=1 .venv/Scripts/python.exe -m uvicorn evidence_rag.main:app --app-dir services/api --port 8000   # API
ENABLE_REAL_MODEL_CALLS=1 .venv/Scripts/python.exe -m evidence_rag.worker                                               # 入库工作进程（在 services/api 目录下运行）
cd apps/web && npm install && npm run dev                                                                               # 前端 :3000

# 7) 灌入演示语料（17 份合成文档；也可在管理页手动上传）
ENABLE_REAL_MODEL_CALLS=1 .venv/Scripts/python.exe evals/tools/run_smoke_baseline.py
```

打开 http://localhost:3000 （登录 demo 账号）——提问、点引用核对原文；http://localhost:3000/kb —— 上传、发布、停用、重试。

## 已实现（真实清单，均有测试或实测记录）

- **认证与会话**：PBKDF2 密码哈希、服务端会话、HttpOnly Cookie、防用户名枚举
- **授权**：401/403/404 三分口径；检索、原文、运行记录、管理操作全链路服务端过滤；未授权文本不进模型上下文（有断言）
- **文档管理**：MD/TXT/PDF 解析（页眉页脚剔除、扫描页显式失败）、分块（标题前缀/重叠/不静默截断）、异步任务（租约/重试/断点续跑）、完全重复检测
- **版本管理**：正文版本不可变（DB 触发器强制）、发布指针原子切换、新旧不混用
- **问答**：契约化六态回答（含拒答不伪造引用、编造引用整体拦截、生成期间知识变更丢弃）、检索模式可切换（精确向量 / 向量+BM25+RRF 混合）
- **运行记录**：检索/生成耗时、token、错误分类、引用与片段快照
- **测试**：93 项自动化测试（对真实 PostgreSQL，无网络全绿）
- **评测**：冒烟集 9/9 pass（经作者复核转正）、A/B 对照报告、六类 badcase 归因、一次有完整证据链的提示词优化迭代（7/9 → 9/9，见 [docs/optimization-log.md](docs/optimization-log.md)）

## 明确未实现

成员管理界面、日志/导出全量脱敏、多轮追问、关键词检索的正式 A/B 结论（80 条主集草稿待作者复核后冻结）、用户验证、公开部署。规划细节见 [docs/implementation-backlog.md](docs/implementation-backlog.md)。

## 文档索引

- [实施方案](docs/implementation-plan.md) · [任务清单](docs/implementation-backlog.md) · [评测口径](docs/evaluation-plan.md)
- [模型与费用](docs/model-and-cost.md) · [金标核对](evals/gold-review.md) · [优化迭代记录](docs/optimization-log.md)
- [A/B 对照报告](evals/results/ab-comparison-report.md) · [演示脚本](docs/demo-script.md) · [案例复盘](docs/case-study.md)
- AI 产出物来源与哈希：[PROVENANCE.md](PROVENANCE.md) · 开发方法：见下

## 开发方法

本项目用自建多模型工作台开发：执行模型产出实现与草稿，主脑按可判定验收条件独立验收，不采信执行模型自报的"已完成"；评测先行，规划指标与实测结果分开记录。AI 产出的评审、夹具等材料在 [PROVENANCE.md](PROVENANCE.md) 登记来源与哈希；采纳的结论改写进自己的文档，未采纳的保留标注或删除。

## 许可与边界

以 [MIT License](LICENSE) 开源。语料全部为合成演示数据（`synthetic: true`），不含真实客户资料；模型端点与密钥均在 `.env`（不入库）。

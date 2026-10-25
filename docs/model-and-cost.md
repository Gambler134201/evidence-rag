# 模型配置与费用边界方案（S0-T04）

编制：2026-10-24（ZCode/GLM 会话，经用户授权）。本文记录已确认的产品模型配置与费用边界；未确认项如实标注，不提前写成实测结论。端点地址等连接信息只存于 `.env`（已忽略，不入库）；本文与 `.env.example` 只含变量名与说明。

## 1. 生成模型（已确认）

| 项 | 结论 |
|---|---|
| 来源 | 用户自部署的本地大模型，OpenAI 兼容接口（`/v1/chat/completions`），地址存 `.env` 的 `GENERATION_BASE_URL`，无密钥 |
| 模型名 | `qwen3.8-flash-next-iq3_xxs`（2026-10-24 经 `/v1/models` 确认，加载中状态） |
| 上下文 | 服务端报告 `n_ctx = 262144`（256K）；官方声称值，实际有效上下文按使用情况另测 |
| 模态 | 输入 text + image，输出 text |
| 最小连通 | 已通过（见 [00-model-connectivity.md](00-model-connectivity.md)）：中文问答 1 次、严格 JSON 引用契约 1 次，均符合预期 |
| 费用 | 自有硬件本地推理：单次调用 API 费用为 0；真实成本为电费与硬件占用，按本项目口径记“自有硬件，无 API 账单”，token 用量以响应 `usage` 字段如实记录 |
| 备用 | 若效果不足（评测显示生成类失败 G1/G3 占比高），用户提供 DeepSeek API 密钥作为对照；DeepSeek 仅覆盖生成，不提供 Embedding（见下） |

**部署拓扑与可用性（2026-10-24 补充）**：该端点是 Tailscale 内网中的另一台主机（`*.ts.net`，解析为 100.64.0.0/10 网段，实测延迟约 91ms），不在开发机上。对本项目而言它是“自有的 OpenAI 兼容端点”——开发机与模型主机的物理位置、调用者在哪里均不影响接入方式；只要双方都在 tailnet 内即可连通（2026-10-24 两次实测均处于“调用者不在模型主机本地”的场景）。**可用性约束**：生成端点在线取决于该主机开机且推理服务在运行；主机离线或休眠时生成调用会失败，服务端按实施方案的超时与错误分类处理，记为 `error` 状态，不视为知识库无答案。

## 2. Embedding 模型（已选型：硅基流动云端 bge-m3 免费档；待密钥后验证）

**决策（2026-10-24，用户选定）**：采用云端 Embedding API——硅基流动 SiliconFlow 标准版 `BAAI/bge-m3`。选择理由：该模型当前在价格页标为免费（收费的是 `Pro/BAAI/bge-m3` 变体，¥0.07/百万 token，本项目不采用）、1024 维、单条输入上限 8192 token、OpenAI 兼容接口与国内直连。接口为 `https://api.siliconflow.cn/v1/embeddings`（国际站为 api.siliconflow.com，本项目用国内域名）。

- **已配置**：`.env` 中 `EMBEDDING_BASE_URL / EMBEDDING_MODEL / EMBEDDING_DIMENSION=1024` 已填，`EMBEDDING_API_KEY` 待用户在控制台创建后填入（密钥只存 `.env`，不入库）。
- **注意**：bge-m3 不支持 `dimensions` 参数（传入返回 400）；调用端不得发送该参数，维度一致性以 `EMBEDDING_DIMENSION` 硬校验（脚本 `evals/tools/probe_embedding.py` 已实现）。
- **待办**：用户创建密钥 → 运行 `probe_embedding.py` → 结果摘录进 `00-model-connectivity.md` 补 S0-T06 Embedding 半项 → 解锁 S1-T05。
- **费用口径**：标准版免费，费用记 0 并注明“免费标准版 + 记录日期”；若误用 Pro 变体会产生 ¥0.07/M 费用，调用时模型名必须精确为 `BAAI/bge-m3`。
- **2026-10-25 事件**：账户返回 402（余额不足），免费模型调用一并被拒——欠费状态下免费模型也会停用。待充值或更换密钥后，`run_eval --mode rerank` 复验即可恢复；期间 Embedding 相关验证暂停（如实记录，不猜测恢复时间）。另修复：重排请求曾误用 Embedding 模型名（400 model-does-not-exist），客户端已改为独立 rerank_model 字段。
- **本地部署 bge-m3 保留为后备**：若云端免费档未来取消或网络不稳，可本地部署（GGUF Q8 约 600 MB），配置只需换 `.env` 三个变量。

**背景（原始选项记录）**：本地生成端点不提供 `/v1/embeddings`（2026-10-24 实测 404）；DeepSeek 官方 API 也没有 Embedding 接口。备选方案：本地部署 bge-m3（零 API 费用、数据不出本机）或云端 API（需注册与密钥）。用户选定后者。

## 3. 费用记录规则（沿用实施方案 §8）

- 费用按真实提供方用量与已核实单价计算，记录日期与币种；缺用量或免费额度信息时记 `未知`，不填 0。
- 本地模型的每次调用记录 token 用量（响应 `usage` 已提供），费用列记“自有硬件，无 API 账单”。
- `.env` 与密钥不入 Git；`.env.example` 只给变量名。
- 不占用、不重启正在为其他项目服务的模型进程；本轮仅通过 HTTP 接口调用，未触碰用户本地推理服务本身。

## 4. `.env` 变量约定

| 变量 | 用途 | 状态 |
|---|---|---|
| `GENERATION_BASE_URL` / `GENERATION_MODEL` / `GENERATION_API_KEY`（可空） | 生成模型连接 | 已确认（值在本机 `.env`） |
| `EMBEDDING_BASE_URL` / `EMBEDDING_MODEL` / `EMBEDDING_API_KEY` / `EMBEDDING_DIMENSION` | Embedding 连接与维度校验 | 待选型后填写 |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` / `POSTGRES_PORT` | 项目专用 PostgreSQL（docker-compose） | 容器路线已批准，待 Docker Desktop 就绪后启用 |
| `ENABLE_REAL_MODEL_CALLS` | 真实模型调用显式开关（S1-T11），默认 `0` | 约定，代码实现时生效 |

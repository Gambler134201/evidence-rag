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

## 2. Embedding 模型（待定，阻塞 S1-T05 真实向量写入）

**现状**：本地生成端点不提供 `/v1/embeddings`（2026-10-24 实测 404）；DeepSeek 官方 API 也没有 Embedding 接口。Embedding 必须另行解决。

| 选项 | 说明 | 代价 / 风险 |
|---|---|---|
| A（建议） | 本地再部署一个 Embedding 模型，候选 `BAAI/bge-m3`（1024 维，中文效果好，原方案已列为对照候选）；llama.cpp / Ollama 均可挂载 | 零 API 费用、数据不出本机；需要用户再部署一个模型服务，占用少量显存/内存 |
| B | 云端 Embedding API（如硅基流动 bge-m3 免费档、阿里 DashScope text-embedding-v3 等国内可直连提供方） | 需注册与密钥；语料上传到第三方；费用低但非 0，需按 S0-T04 费用规则记录 |

**选定前的边界**：S1-T05 的真实向量写入保持阻塞，只允许 mock Embedding 跑链路（S1-T11）；冒烟题基线（S1-T10）在 Embedding 选定后执行。选定后把模型名、维度、部署方式回填本文，并锁定配置。

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

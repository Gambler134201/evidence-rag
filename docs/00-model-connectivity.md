# 最小连通验证记录（S0-T06）

核对日期：2026-10-24（ZCode/GLM 会话，用户授权）。只做最小请求：每类 1～2 次，不压测、不批量调用。端点地址存于本机 `.env`，本记录以「本地 tailnet 端点」代称，不写入连接串。

## 1. 生成模型：已验证

| 项 | 结果 |
|---|---|
| 提供方 / 模型 | 用户本地自部署，`qwen3.8-flash-next-iq3_xxs`（`/v1/models` 返回唯一模型，`n_ctx=262144`，输入 text+image） |
| 接口 | OpenAI 兼容 `/v1/chat/completions`，无需密钥 |
| 请求 1（中文问答） | HTTP 200。问“用一句话回答：什么是 RAG？不要使用列表”，回答为一句话且未用列表，内容准确；usage：prompt 64 / completion 81 tokens |
| 请求 2（JSON 引用契约） | HTTP 200。系统指令要求只输出 JSON、仅引用给定证据编号；输出为可解析的严格 JSON，`status=answered`，`citation_ids=["C1"]`，答案“3个工作日”与证据一致；usage：prompt 156 / completion 132 tokens |
| 费用 | 本地自有硬件，无 API 账单 |
| 结论 | 生成模型最小连通通过；M1 可用该端点接入真实链路，效果待 10 条样例基线再评估 |

## 2. Embedding：未通过（接口不存在）

- `POST /v1/embeddings` 返回 HTTP 404 `{"error": {"message": "not found"}}`：该端点不提供 Embedding 服务。
- DeepSeek 官方 API 亦无 Embedding 接口（仅 chat/reasoner），用户提供的备用密钥不能解决 Embedding。
- 影响与选项见 [model-and-cost.md](model-and-cost.md) 第 2 节：建议本地再部署 `BAAI/bge-m3`（或等效中文 Embedding 模型），或选用云端 Embedding API。选定前 S1-T05 真实向量写入保持阻塞，仅允许 mock。

## 3. 明确未执行

- 未压测、未批量调用、未测上下文上限（256K 为服务端声称值）；未调用 DeepSeek；未修改用户本地推理服务；未把端点地址写入任何入库文件。
- 本次最小连通不等于 RAG 效果验证，也不能替代 S0-T06 对 Embedding 的验证要求（该半项保持 `待配置`）。

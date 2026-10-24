#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe_embedding.py — S0-T06 Embedding 半项最小连通验证。

读取仓库根 .env 的 EMBEDDING_* 配置，向 /v1/embeddings 发送 1 次中文最小请求，
实测向量维度、延迟与用量。注意：bge-m3 不支持 dimensions 参数（传入返回 400），
本脚本不发送该参数；维度一致性用 .env 的 EMBEDDING_DIMENSION 做硬校验。

运行：.venv/Scripts/python.exe evals/tools/probe_embedding.py
退出码：0 = 通过；1 = 配置缺失或请求失败或维度不符（fail-loud）。
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_env(path):
    env = {}
    if not os.path.exists(path):
        return env
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def main():
    env = load_env(os.path.join(ROOT, ".env"))
    base = env.get("EMBEDDING_BASE_URL", "").rstrip("/")
    model = env.get("EMBEDDING_MODEL", "")
    key = env.get("EMBEDDING_API_KEY", "")
    expect_dim = int(env.get("EMBEDDING_DIMENSION", "0") or 0)

    missing = [n for n, v in
               [("EMBEDDING_BASE_URL", base), ("EMBEDDING_MODEL", model),
                ("EMBEDDING_API_KEY", key)] if not v]
    if missing:
        print(f"缺少配置：{', '.join(missing)} —— 请填入仓库根 .env 后重试（fail-loud，不做任何猜测）")
        return 1

    payload = {"model": model, "input": "验收期限从完整交付的次一工作日起算。"}
    req = urllib.request.Request(
        base + "/embeddings",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})

    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:400]}")
        return 1
    except urllib.error.URLError as e:
        print(f"连接失败：{e}")
        return 1
    dt_ms = (time.time() - t0) * 1000

    item = body["data"][0]
    dim = len(item["embedding"])
    usage = body.get("usage", {})
    ok_dim = (dim == expect_dim) if expect_dim else None
    print(f"提供方/模型: {base} | {model}")
    print(f"HTTP 200，耗时 {dt_ms:.0f} ms")
    print(f"实测维度: {dim}"
          + (f"（与 .env 声明 {expect_dim} 一致）" if ok_dim else
             (f"（与 .env 声明 {expect_dim} 不一致，需核对）" if expect_dim else "（.env 未声明维度，未做硬校验）")))
    print(f"usage: {usage}")
    if ok_dim is False:
        print("FAIL：维度与配置不符，禁止用于建索引")
        return 1
    print("OK：Embedding 最小连通通过。请把本输出如实摘录进 docs/00-model-connectivity.md（含日期与免费/付费口径）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

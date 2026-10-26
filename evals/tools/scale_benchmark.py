"""阶段 E：规模压测（合成向量，不依赖任何外部 API）。

在独立表 scale_bench（用后即删）上测：
- 1k/5k/20k 三个规模点的精确向量检索 P50/P95（30 次查询）；
- 同规模下 HNSW 索引的构建耗时与检索 P50/P95（对比 ANN 收益与召回代价的决策依据）；
- 内存 BM25（当前实现）在 2 万文档上的构建/查询耗时——验证"规模上限"结论；
- 批量写入吞吐（真实入库体验的近似）。

全部使用合成向量（随机归一化），语义质量无关——测的是索引性能。
"""
import statistics
import sys
import time

import numpy as np
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2] / "services" / "api"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import text  # noqa: E402

from evidence_rag.db import engine  # noqa: E402
from evidence_rag.retrieval import _tokenize  # noqa: E402

SCALES = [1000, 5000, 20000]
DIM = 1024
N_QUERIES = 30
SEED = 42


def norm_vec(rng) -> list[float]:
    v = rng.standard_normal(DIM)
    n = float(np.linalg.norm(v)) or 1.0
    return (v / n).tolist()


def doc_text(i: int) -> str:
    return f"占位文档 {i}：交付规则与验收期限说明，用于 BM25 容量压测的合成正文段落 {i}。"


def main() -> int:
    import json

    rng = np.random.default_rng(SEED)
    results = {"insert_s_per_k": {}, "exact": {}, "hnsw_build_s": None, "hnsw": {}, "bm25": {}}

    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS scale_bench"))
        conn.execute(text(f"CREATE TABLE scale_bench (id bigserial PRIMARY KEY, embedding vector({DIM}))"))

    print(f"开始压测：目标 {max(SCALES)} 行，维度 {DIM}")

    inserted = 0
    marks = sorted(SCALES)
    batch = 500
    while inserted < max(SCALES):
        t0 = time.perf_counter()
        vecs = [norm_vec(rng) for _ in range(batch)]
        with engine.begin() as conn:
            for v in vecs:
                conn.execute(text("INSERT INTO scale_bench (embedding) VALUES (CAST(:v AS vector))"),
                             {"v": "[" + ",".join(f"{x:.4f}" for x in v) + "]"})
        inserted += len(vecs)
        if inserted in marks or (inserted > marks[-1] and inserted % 1000 < batch):
            pass
        for m in marks:
            if inserted >= m and f"{m}" not in results["insert_s_per_k"] and inserted - batch < m <= inserted:
                results["insert_s_per_k"][m] = round(time.perf_counter() - t0, 2)
                print(f"  已插入 {inserted} 行（本批 {batch} 行耗时 {time.perf_counter()-t0:.1f}s）")

    queries = [norm_vec(rng) for _ in range(N_QUERIES)]

    def measure_exact(n_rows):
        times = []
        for qv in queries:
            t0 = time.perf_counter()
            with engine.connect() as conn:
                conn.execute(text("""
                    SELECT id FROM scale_bench
                    ORDER BY embedding <=> CAST(:v AS vector) LIMIT 5
                """), {"v": "[" + ",".join(f"{x:.4f}" for x in qv) + "]"}).all()
            times.append((time.perf_counter() - t0) * 1000)
        return {"P50": round(statistics.median(times), 1), "P95": round(sorted(times)[int(N_QUERIES*0.95)-1], 1)}

    for m in SCALES:
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM scale_bench WHERE id > :n"), {"n": m})
        results["exact"][m] = measure_exact(engine)
        print(f"  精确检索 @ {m} 行: {results['exact'][m]}")

    for m in SCALES:
        t0 = time.perf_counter()
        try:
            with engine.begin() as conn:
                conn.execute(text(
                    "CREATE INDEX hnsw_bench ON scale_bench USING hnsw (embedding vector_cosine_ops)"
                    f" WITH (m = 16, ef_construction = 64)"
                )) if m == max(SCALES) else None
        except Exception as exc:
            print(f"  HNSW 构建失败: {exc}")
        dt = time.perf_counter() - t0
        if m == max(SCALES):
            results["hnsw_build_s"] = round(dt, 2)
            for qv in queries:
                times = []
                for _ in range(N_QUERIES):
                    t1 = time.perf_counter()
                    with engine.connect() as conn:
                        conn.execute(text("""
                            SELECT id FROM scale_bench
                            ORDER BY embedding <=> CAST(:v AS vector) LIMIT 5
                        """), {"v": "[" + ",".join(f"{x:.4f}" for x in qv) + "]"}).all()
                    times.append((time.perf_counter() - t1) * 1000)
            results["hnsw"][max(SCALES)] = {"P50": round(statistics.median(times), 1),
                                            "P95": round(sorted(times)[int(N_QUERIES*0.95)-1], 1)}
            print(f"  HNSW 构建 {results['hnsw_build_s']}s @ 20k；检索 {results['hnsw'][max(SCALES)]}")
            break

    # 内存 BM25 容量（当前实现的规模上限验证）
    print("内存 BM25 容量测试（2 万文档）…")
    docs = [doc_text(i) for i in range(20000)]
    t0 = time.perf_counter()
    tok = [_tokenize(d) for d in docs]
    t_tok = time.perf_counter() - t0
    from rank_bm25 import BM25Okapi
    t0 = time.perf_counter()
    bm25 = BM25Okapi(tok)
    t_build = time.perf_counter() - t0
    t0 = time.perf_counter()
    for _ in range(20):
        bm25.get_scores(_tokenize("验收期限是几个工作日"))
    t_query = (time.perf_counter() - t0) / 20 * 1000
    results["bm25"] = {"tokenize_20k_s": round(t_tok, 1), "build_20k_s": round(t_build, 1),
                       "query_ms_avg": round(t_query, 1)}
    print(f"  BM25 2 万文档：分词 {results['bm25']['tokenize_20k_s']}s，构建 {results['bm25']['build_20k_s']}s，单查询 {results['bm25']['query_ms_avg']}ms")

    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS scale_bench"))

    report = ["# 阶段 E：规模压测报告（合成向量，2026-10-25）", "",
              f"> 维度 {DIM}；每点 {N_QUERIES} 次查询；种子 {SEED} 可复现；压测表用后即删。", "",
              "| 规模 | 精确检索 P50/P95 (ms) | HNSW P50/P95 (ms) | 批量写入 (s/500行) |", "|---|---|---|---|"]
    for m in SCALES:
        ex = results["exact"][m]
        hn = results["hnsw"].get(m, "—")
        hn_s = f"{hn['P50']}/{hn['P95']}" if isinstance(hn, dict) else "—"
        ins = results["insert_s_per_k"].get(m, "—")
        out_row = f"| {m} | {ex['P50']}/{ex['P95']} | {hn_s} | {ins} |"
        report.append(out_row)
    report += ["", f"- HNSW 构建（20k）：{results['hnsw_build_s']}s",
               f"- 内存 BM25（2 万文档）：分词 {results['bm25']['tokenize_20k_s']}s、构建 {results['bm25']['build_20k_s']}s、单查询 {results['bm25']['query_ms_avg']}ms",
               "", "## 读数（待写报告时结合数据）", "",
               "- 精确检索在本机规模下延迟可接受与否，决定 ANN 引入时机（原规划的触发条件实测）；",
               "- BM25 2 万文档构建/查询耗时验证内存实现的规模上限；",
               "- 写入吞吐为真实入库体验的参考基线。"]

    (REPO / "evals/results/scale-benchmark.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    (REPO / "evals/results/scale-benchmark-data.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("报告: evals/results/scale-benchmark.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())

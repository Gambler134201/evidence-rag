#!/usr/bin/env bash
# 开发环境恢复：Docker Desktop → 数据库容器 → 就绪确认。
# 用法：bash scripts/dev_up.sh
set -e
DOCKER="/c/Program Files/Docker/Docker/resources/bin/docker.exe"

if "$DOCKER" info >/dev/null 2>&1; then
    echo "Docker 引擎已在运行"
else
    echo "启动 Docker Desktop…"
    "/c/Program Files/Docker/Docker/Docker Desktop.exe" &
    for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
        if "$DOCKER" info >/dev/null 2>&1; then echo "  引擎就绪（第 $i 次探测）"; break; fi
        sleep 8
    done
fi

"$DOCKER" start evidence-rag-db 2>/dev/null || true
for i in 1 2 3 4 5 6; do
    if "$DOCKER" exec evidence-rag-db pg_isready -U evidence_rag 2>/dev/null | grep -q accepting; then
        echo "数据库就绪"
        exit 0
    fi
    echo "  等待数据库… $i"
    sleep 6
done
echo "数据库未能就绪，请检查 docker logs evidence-rag-db"
exit 1

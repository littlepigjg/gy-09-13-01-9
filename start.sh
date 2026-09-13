#!/bin/bash
set -e
cd "$(dirname "$0")"

# 在 Docker Hub 访问受限的环境下，BuildKit 解析远端镜像元数据可能超时；
# 使用传统 builder（本地已有基础镜像）构建，规避该问题。
export DOCKER_BUILDKIT=0

echo "==> 构建后端镜像 audit-backend:latest"
docker build -t audit-backend:latest ./backend

echo "==> 构建前端镜像 audit-frontend:latest"
docker build -t audit-frontend:latest ./frontend

echo "==> 启动服务"
docker compose up -d

echo ""
echo "启动完成："
echo "  前端:  http://localhost:5173"
echo "  后端API文档: http://localhost:8010/docs"
echo "  MySQL: localhost:13306 (root / root)"

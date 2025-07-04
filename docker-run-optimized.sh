#!/bin/bash

# Docker优化启动脚本 - 适用于python:3.11-slim环境
# 用于解决网络连接问题和提高爬虫稳定性

echo "正在停止现有容器..."
docker stop 98tang-crawler 2>/dev/null || true
docker rm 98tang-crawler 2>/dev/null || true

echo "正在构建Docker镜像..."
docker build -t 98tang-crawler .

if [ $? -ne 0 ]; then
    echo "Docker镜像构建失败！"
    exit 1
fi

echo "正在启动优化的Docker容器..."
docker run -d \
    --name 98tang-crawler \
    --memory=2g \
    --cpus=1.5 \
    --shm-size=512m \
    --ulimit nofile=65536:65536 \
    --ulimit nproc=4096:4096 \
    --security-opt seccomp=unconfined \
    --cap-add=SYS_ADMIN \
    -p 8105:8105 \
    -v "$(pwd)/data:/app/data" \
    -v "$(pwd)/logs:/app/logs" \
    -e MICRO_ENV=docker \
    -e CHROME_BIN=/usr/bin/chromium \
    -e CHROMEDRIVER_PATH=/usr/bin/chromedriver \
    -e PYTHONUNBUFFERED=1 \
    -e TZ=Asia/Shanghai \
    98tang-crawler

if [ $? -eq 0 ]; then
    echo "容器启动成功！"
    echo "Web界面: http://localhost:8105"
    echo ""
    echo "查看日志: docker logs -f 98tang-crawler"
    echo "进入容器: docker exec -it 98tang-crawler /bin/bash"
    echo "网络测试: docker exec -it 98tang-crawler python test_network_connection.py"
else
    echo "容器启动失败！"
    exit 1
fi
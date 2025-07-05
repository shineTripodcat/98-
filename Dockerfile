# 基于更轻量的 debian slim 镜像，自动安装 Chromium/Chromedriver，极致精简
FROM python:3.13-slim

# 安装系统依赖和 Chromium/Chromedriver 及编译工具，安装完依赖后卸载编译工具
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        python3-dev \
        libc-dev \
        chromium \
        chromium-driver \
        ca-certificates \
        fonts-liberation \
        libnss3 \
        libatk-bridge2.0-0 \
        libgtk-3-0 \
        libxss1 \
        libasound2 \
        libgbm1 \
        libu2f-udev \
        libvulkan1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制依赖和代码
COPY requirements.txt ./
# 复制本地python-115文件夹
COPY python-115/ ./python-115/
# 先安装基础依赖，然后从本地安装python-115
RUN pip install --no-cache-dir Flask==2.3.3 flask-socketio==5.3.6 selenium==4.15.2 requests==2.31.0 pandas==2.2.3 APScheduler==3.10.4 beautifulsoup4==4.13.0 psutil==5.9.5 schedule \
    && pip install --no-cache-dir httpx orjson rich yarl \
    && pip install --no-cache-dir p115client>=0.0.5.12.2 \
    && pip install --no-cache-dir httpx_request>=0.0.8.2 magnet2torrent glob_pattern>=0.0.2 posixpatht>=0.0.4 \
    && pip install --no-cache-dir ./python-115/
COPY app.py .
COPY crawler.py .
COPY config_manager.py .
COPY pan115_manager.py .

COPY utils.py .
COPY templates/ ./templates/
COPY static/ ./static/
COPY config/ ./config/

# 创建最小必要目录
RUN mkdir -p /app/data /app/logs \
    && useradd -m appuser \
    && chown -R appuser:appuser /app

# 设置环境变量
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FLASK_APP=app.py \
    FLASK_ENV=production \
    MICRO_ENV=true \
    CHROME_BIN=/usr/bin/chromium \
    CHROMEDRIVER_PATH=/usr/bin/chromedriver \
    TZ=Asia/Shanghai

# 切换到非root用户
USER appuser

# 暴露端口
EXPOSE 8105

# 启动应用
CMD ["python", "app.py"]

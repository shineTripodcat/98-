# 基于更轻量的 debian slim 镜像，自动安装 Chromium/Chromedriver，极致精简
FROM python:3.11-slim

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
RUN pip install --no-cache-dir -r requirements.txt
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

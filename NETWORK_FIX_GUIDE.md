# 网络连接问题修复指南

本指南针对在Docker环境中运行爬虫时遇到的网络连接问题提供解决方案。

## 问题描述

在Docker环境中运行爬虫时，可能遇到以下问题：
- `net::ERR_CONNECTION_RESET` 错误
- 爬取页面TID失败
- Chrome浏览器连接不稳定
- 页面加载超时

## 修复措施

### 1. Chrome浏览器优化

#### 增加稳定性选项
已在 `crawler.py` 中的 `_create_driver` 方法添加以下优化选项：

```python
# 网络稳定性选项
options.add_argument('--disable-background-timer-throttling')
options.add_argument('--disable-backgrounding-occluded-windows')
options.add_argument('--disable-renderer-backgrounding')
options.add_argument('--disable-features=TranslateUI')
options.add_argument('--disable-ipc-flooding-protection')
options.add_argument('--disable-background-networking')
options.add_argument('--disable-default-apps')
options.add_argument('--disable-sync')
options.add_argument('--aggressive-cache-discard')
options.add_argument('--max_old_space_size=4096')
```

#### 超时时间调整
- 页面加载超时：30秒 → 60秒
- 隐式等待时间：10秒 → 15秒
- 设置固定窗口大小：1920x1080

### 2. 重试机制增强

#### 页面访问重试
在 `_get_page_tids()` 方法中添加了重试机制：
- 最多重试3次
- 初始延迟5秒，指数退避
- 使用 `WebDriverWait` 确保页面完全加载

#### 错误检测
增加了对页面内容的检查，检测是否包含：
- "连接被重置"
- "ERR_CONNECTION_RESET"

### 3. 并发控制优化

#### 降低并发数
在 `crawler_config.json` 中调整了以下参数：
- `worker_count`: 5 → 2
- `min_wait_time`: 2 → 5
- `random_delay`: 5 → 10

### 4. 配置文件优化

#### 新增Chrome选项
在 `crawler_config.json` 中添加了 `chrome_options` 配置：

```json
"chrome_options": [
    "--disable-blink-features=AutomationControlled",
    "--disable-web-security",
    "--allow-running-insecure-content",
    "--disable-features=VizDisplayCompositor",
    "--disable-logging",
    "--disable-dev-shm-usage",
    "--no-sandbox",
    "--remote-debugging-port=9222"
]
```

### 5. Docker运行优化

#### 资源限制
使用优化的启动脚本，包含以下配置：
- 内存限制：2GB
- CPU限制：1.5核
- 共享内存：512MB
- ulimit配置：提高文件描述符限制

#### 系统权限
添加必要的安全选项：
- `--security-opt seccomp=unconfined`
- `--cap-add=SYS_ADMIN`

## 使用方法

### 1. 重新部署容器

#### Linux/macOS
```bash
# 使用优化启动脚本
chmod +x docker-run-optimized.sh
./docker-run-optimized.sh
```

#### Windows
```cmd
# 使用优化启动脚本
docker-run-optimized.bat
```

### 2. 网络诊断

运行网络连接测试：
```bash
# 在容器内运行
docker exec -it 98tang-crawler python test_network_connection.py

# 或者在宿主机运行
python test_network_connection.py
```

### 3. 查看日志

```bash
# 查看容器日志
docker logs -f 98tang-crawler

# 查看应用日志
docker exec -it 98tang-crawler tail -f /app/logs/crawler.log
```

## 故障排除

### 常见问题

1. **连接重置错误**
   - 检查代理设置是否正确
   - 确认目标网站是否可访问
   - 尝试降低并发数

2. **找不到TID**
   - 检查论坛页面结构是否变化
   - 确认年龄验证是否正常处理
   - 查看页面源码是否包含预期内容

3. **超时问题**
   - 增加页面加载超时时间
   - 检查网络延迟
   - 考虑使用更稳定的代理

### 调试命令

```bash
# 进入容器调试
docker exec -it 98tang-crawler /bin/bash

# 检查Chrome进程
ps aux | grep chrome

# 检查网络连接
netstat -an | grep :7890

# 测试代理连接
curl -x http://192.168.50.1:7890 https://httpbin.org/ip
```

## 监控建议

1. **定期检查日志**
   - 监控错误频率
   - 关注超时情况
   - 跟踪成功率变化

2. **性能指标**
   - 页面加载时间
   - TID获取成功率
   - 内存和CPU使用情况

3. **网络状态**
   - 代理连接稳定性
   - 目标网站响应时间
   - DNS解析时间

## 性能优化建议

1. **进一步降低并发**
   - 如果仍有问题，可将 `worker_count` 降至1
   - 增加 `min_wait_time` 到10秒

2. **使用更稳定的代理**
   - 考虑使用多个代理轮换
   - 监控代理响应时间

3. **优化Docker资源**
   - 根据实际需要调整内存限制
   - 监控容器资源使用情况

4. **定期重启**
   - 设置定时重启任务
   - 清理Chrome进程和缓存

## 注意事项

- 本修复基于 `python:3.11-slim` Docker镜像
- 所有配置已针对Debian环境优化
- 建议在生产环境中逐步调整参数
- 定期备份配置文件和数据
# 98Tang Web Crawler - 轻量版 Docker 部署

## ⚠️ 免责声明

**本项目所有代码来源于AI生成，本人不懂任何代码，也不会维护。**

- 代码由AI助手生成，可能存在未知问题
- 作者不具备编程能力，无法提供技术支持
- 使用本项目请自行承担风险
- 不保证代码的稳定性和安全性
- 如有问题请自行解决或寻求其他技术支持

## 快速开始

### 使用 Docker Compose（推荐）

```bash
# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

### 使用 Docker 命令

```bash
# 直接使用预构建镜像
docker run -d \
  --name web-crawler-98tang \
  -p 8105:8105 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/config:/app/config \
  -e TZ=Asia/Shanghai \
  shine1223/98t:latest
```

## 访问应用

- Web界面: http://localhost:8105


## 特性

- 支持转存115网盘指定目录
- 支持最多10个并发爬虫任务
- 内置任务管理和状态监控
- 实时进度跟踪
- 数据持久化存储

## 目录结构

- `/app/data` - 爬取结果存储
- `/app/logs` - 应用日志
- `/app/config` - 配置文件

## 健康检查

容器启动后会自动进行健康检查，确保应用正常运行。

# PDD Crawler - 拼多多商家后台数据采集工具

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688)](https://fastapi.tiangolo.com/)
[![Playwright](https://img.shields.io/badge/Playwright-1.40%2B-009688)](https://playwright.dev/)
[![版本](https://img.shields.io/badge/版本-0.3.0-green)](https://github.com/reopan02/pdd_crawler)

基于 Web 界面的拼多多商家后台数据采集工具。每个店铺对应一个 Docker 容器中的 Chrome 浏览器，通过 CDP (Chrome DevTools Protocol) 连接执行操作。

## 功能

- **店铺管理** — 配置 Chrome 容器，支持多店铺
- **QR 登录** — 通过 CDP 截图推送二维码到 Web 端扫码登录
- **登录验证** — 验证 MMS 登录态 + Cashier SSO 会话
- **首页数据抓取** — 采集商家后台首页的店铺经营数据
- **账单导出** — 导出资金流水 (4001) 和订单交易 (4002) 账单
- **数据清洗** — 对采集的原始数据进行清洗，生成结构化日报并下载

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.10+ / FastAPI / Uvicorn / Playwright |
| 前端 | React SPA (内嵌 static/index.html) |
| 浏览器 | Docker Chrome + CDP (connect_over_cdp) |
| 通信 | REST API + SSE (Server-Sent Events) |

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│                        Web 浏览器                            │
│   (业务人员访问 http://<IP>:8000 操作)                        │
└─────────────────────┬───────────────────────────────────────┘
                      │ HTTP / SSE
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                     FastAPI 后端                             │
│   ├── /api/shops/*      — 店铺管理、登录、验证                │
│   ├── /api/crawl/*      — 采集任务管理                       │
│   └── /api/clean/*      — 数据清洗                           │
└─────────────────────┬───────────────────────────────────────┘
                      │ playwright.connect_over_cdp()
                      ▼
┌─────────────────────────────────────────────────────────────┐
│               Chrome 容器 (每个店铺一个)                       │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│   │ chrome-shop1│  │ chrome-shop2│  │ chrome-shop3│  ...    │
│   │  :9222/CDP  │  │  :9223/CDP  │  │  :9224/CDP  │         │
│   │  :6080/VNC  │  │  :6081/VNC  │  │  :6082/VNC  │         │
│   └─────────────┘  └─────────────┘  └─────────────┘         │
└─────────────────────────────────────────────────────────────┘
```

## 快速开始

### 前置要求

- Docker + Docker Compose
- Python 3.10+

### 1. 配置店铺

编辑 `src/pdd_crawler/config.py` 中的 `CHROME_ENDPOINTS`：

```python
CHROME_ENDPOINTS = [
    ChromeEndpoint(
        shop_id="shop1",
        shop_name="店铺1",
        cdp_url="http://localhost:9222",
        vnc_url="http://localhost:6080",
    ),
    # 添加更多店铺...
]
```

或通过环境变量覆盖：

```bash
export CHROME_SHOP1_CDP=http://192.168.1.100:9222
export CHROME_SHOP1_VNC=http://192.168.1.100:6080
```

### 2. 启动服务

```bash
# 构建并启动所有容器
docker-compose up -d

# 查看状态
docker-compose ps

# 查看日志
docker-compose logs -f backend
```

### 3. 访问 Web 界面

访问 `http://localhost:8000` 或局域网 `http://<IP>:8000`。

### 4. 首次登录

1. 点击店铺卡片 → "登录"
2. 手机拼多多 APP 扫描二维码
3. 登录态保存在容器持久化卷中，后续无需重复登录

## 项目结构

```
pdd_crawler/
├── src/pdd_crawler/
│   ├── __main__.py                 # CLI 入口
│   ├── config.py                   # 配置常量 (URL、店铺定义)
│   ├── chrome_pool.py              # CDP 连接池管理
│   ├── shop_manager.py             # 登录验证逻辑
│   ├── home_scraper.py             # 首页数据抓取
│   ├── bill_exporter.py            # 账单导出
│   └── web/
│       ├── app.py                  # FastAPI 应用
│       ├── deps.py                 # 共享依赖 (chrome_pool)
│       ├── session_store.py        # 内存会话存储
│       ├── shop_api.py             # 店铺管理 API
│       ├── task_api.py             # 采集任务 API
│       ├── clean_api.py            # 数据清洗 API
│       └── static/index.html       # React SPA 前端
├── docker/
│   └── chrome/
│       ├── Dockerfile              # Chrome 容器镜像
│       └── entrypoint.sh           # 启动脚本
├── docker-compose.yml              # 容器编排
├── pyproject.toml
└── README.md
```

## API

### 店铺管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/shops` | 列出所有店铺及连接/登录状态 |
| GET | `/api/shops/{shop_id}` | 获取单个店铺状态 |
| POST | `/api/shops/{shop_id}/login` | 启动 QR 登录 |
| GET | `/api/shops/{shop_id}/login/{task_id}/stream` | SSE：推送二维码 |
| POST | `/api/shops/{shop_id}/validate` | 验证登录态 |
| POST | `/api/shops/validate-all` | 验证所有店铺 |
| GET | `/api/shops/validate-all/stream` | SSE：验证进度 |

### 采集任务

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/crawl/start` | 启动采集 (`{"shop_ids": [...], "operations": [...]}`) |
| GET | `/api/tasks` | 列出所有任务 |
| GET | `/api/tasks/{id}` | 查询任务状态和结果 |
| GET | `/api/tasks/{id}/progress` | SSE：实时进度 |
| GET | `/api/tasks/{id}/result` | 获取任务完整数据 |

### 数据清洗

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/clean` | 直接传入数据进行清洗 |
| POST | `/api/clean/from-task/{id}` | 从任务结果清洗 |
| POST | `/api/clean/download` | 生成并下载 JSON 日报 |

### 其他

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 (含店铺连接状态) |

## 数据清洗 API

详情见 [数据清洗说明](./docs/data_cleaning.md)

## 注意事项

1. **登录态持久化** — 登录态保存在 Docker 卷中，重启容器后保留
2. **安全环境** — 请在可信的局域网环境中使用，API 未设鉴权
3. **频率控制** — 避免过于频繁地访问拼多多后台，以免触发风控
4. **仅供学习** — 本工具仅供学习交流使用，请遵守相关法律法规

## 开发

### 本地开发模式（不使用 Docker）

```bash
# 安装依赖
pip install -e .

# 手动启动 Chrome 容器
docker run -d --name pdd-chrome-dev \
  -p 9222:9222 -p 6080:6080 \
  -v pdd-chrome-data:/home/chrome/chrome-data \
  pdd-chrome:latest

# 启动后端
python -m pdd_crawler
```

### 构建 Chrome 容器镜像

```bash
cd docker/chrome
docker build -t pdd-chrome:latest .
```

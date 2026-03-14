# PDD Crawler - 拼多多商家后台数据采集工具

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688)](https://fastapi.tiangolo.com/)
[![版本](https://img.shields.io/badge/版本-0.2.0-green)](https://github.com/reopan02/pdd_crawler)

基于 Web 界面的拼多多商家后台数据采集工具。所有数据仅在内存中运行，不写入本地文件，支持局域网多用户访问。

## 功能

- **Cookie 管理** — 上传 Playwright storage_state JSON / 扫码登录，在线验证有效性
- **首页数据抓取** — 采集商家后台首页的店铺经营数据
- **账单导出** — 导出资金流水 (4001) 和订单交易 (4002) 账单
- **数据清洗** — 对采集的原始数据进行清洗，生成结构化日报并下载

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.8+ / FastAPI / Uvicorn |
| 前端 | React SPA (内嵌 static/index.html) |
| 爬虫 | crawl4ai + Playwright (Chromium) |
| 通信 | REST API + SSE (Server-Sent Events) |

## 快速开始

### 安装

```bash
pip install -e .
playwright install chromium
```

### 启动

```bash
# 前台运行 (默认 0.0.0.0:8000)
python -m pdd_crawler

# 指定端口
python -m pdd_crawler --port 9000

# 指定监听地址
python -m pdd_crawler --host 127.0.0.1 --port 8080
```

访问 `http://localhost:8000` 或局域网 `http://<本机IP>:8000`。

### 后台运行 (WSL / Linux)

```bash
chmod +x start.sh

./start.sh            # 启动
./start.sh stop       # 停止
./start.sh restart    # 重启
./start.sh status     # 查看状态
./start.sh log        # 实时查看日志
```

自定义地址和端口：

```bash
PDD_HOST=127.0.0.1 PDD_PORT=9000 ./start.sh
```

日志输出到 `logs/` 目录，PID 记录在 `logs/web.pid`。

## 项目结构

```
pdd_crawler/
├── src/pdd_crawler/
│   ├── __main__.py                 # CLI 入口，启动 Web 服务
│   ├── config.py                   # 配置常量 (URL、超时、反检测)
│   ├── cookie_manager.py           # Cookie 管理与浏览器认证
│   ├── home_scraper.py             # 首页数据抓取 (JS 注入提取)
│   ├── crawl4ai_bill_exporter.py   # 账单导出 (SSO + 下载)
│   └── web/
│       ├── app.py                  # FastAPI 应用 (CORS、路由挂载)
│       ├── deps.py                 # 共享依赖 (会话ID、浏览器信号量)
│       ├── session_store.py        # 内存会话存储 (多用户隔离)
│       ├── cookie_api.py           # Cookie 上传/验证/删除/扫码登录
│       ├── task_api.py             # 采集任务管理 (SSE 进度推送)
│       ├── clean_api.py            # 数据清洗与日报生成
│       ├── run.py                  # 备用启动入口
│       └── static/index.html       # React SPA 前端
├── start.sh                        # WSL/Linux 后台启动脚本
├── tests/
├── pyproject.toml
└── README.md
```

## API

### Cookie 管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/cookies/upload` | 上传 storage_state JSON 文件 |
| GET | `/api/cookies` | 列出当前会话所有 Cookie |
| POST | `/api/cookies/{id}/validate` | 启动浏览器验证 Cookie 有效性 |
| POST | `/api/cookies/{id}/rename` | 重命名店铺名称 |
| DELETE | `/api/cookies/{id}` | 删除 Cookie |

### 扫码登录

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/qr-login/start` | 启动扫码登录，返回 task_id |
| GET | `/api/qr-login/{id}/stream` | SSE 流：推送二维码截图和登录状态 |

### 采集任务

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/crawl/start` | 启动采集任务 (首页抓取 + 账单导出) |
| GET | `/api/tasks` | 列出所有任务 |
| GET | `/api/tasks/{id}` | 查询任务状态和结果 |
| GET | `/api/tasks/{id}/progress` | SSE 流：实时进度推送 |
| GET | `/api/tasks/{id}/result` | 获取任务完整数据 |

### 数据清洗

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/clean` | 直接传入数据进行清洗 |
| POST | `/api/clean/from-task/{id}` | 从已完成任务的结果中清洗 |
| POST | `/api/clean/download` | 生成并下载清洗后的 JSON 日报 |

### 其他

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |

## 架构说明

### 数据流

```
上传 Cookie / 扫码登录
        ↓
  内存会话存储 (SessionStore)
        ↓
  启动采集任务 → crawl4ai + Playwright → 内存中的原始数据
        ↓
  数据清洗 → 结构化日报 JSON
        ↓
  浏览器下载 (不落盘)
```

### 多用户隔离

通过 `X-Session-ID` 请求头实现会话隔离，每个会话独立维护 Cookie 列表、任务队列和采集结果。未指定时使用 `default` 会话。

### 浏览器并发控制

通过 `asyncio.Semaphore(2)` 限制最多同时运行 2 个浏览器实例，防止资源耗尽。

## 注意事项

1. **数据不持久化** — 所有数据仅存于内存，服务重启后丢失，请及时下载
2. **安全环境** — 请在可信的局域网环境中使用，API 未设鉴权
3. **频率控制** — 避免过于频繁地访问拼多多后台，以免触发风控
4. **仅供学习** — 本工具仅供学习交流使用，请遵守相关法律法规

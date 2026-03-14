# PDD Crawler - 拼多多商家后台数据采集工具 (Web 版)

[![Python版本](https://img.shields.io/badge/Python-3.8%2B-blue)](https://www.python.org/)
[![项目版本](https://img.shields.io/badge/版本-0.2.0-green)](https://pypi.org/)

## 项目简介

PDD Crawler 是一个用于采集拼多多商家后台数据的 Web 工具。通过浏览器界面完成：

1. **Cookie 管理** - 上传/扫码登录获取 Cookie，验证有效性
2. **首页数据抓取** - 采集商家后台首页的店铺信息和经营数据
3. **账单导出** - 导出并下载商家的账单文件（4001/4002）
4. **数据清洗** - 对采集数据进行清洗，生成日报

> **特性**：所有数据仅在内存中运行，不写入本地文件。支持多用户、局域网访问。

## 快速开始

```bash
# 安装依赖
pip install -e .
playwright install chromium

# 启动 Web 服务
python -m pdd_crawler
# 访问 http://localhost:8000
```

指定端口：`python -m pdd_crawler --port 9000`

## 项目结构

```
pdd_crawler/
├── src/pdd_crawler/
│   ├── __main__.py              # Web 服务入口
│   ├── config.py                # 配置和常量
│   ├── cookie_manager.py        # Cookie 管理与认证
│   ├── home_scraper.py          # 首页数据抓取
│   ├── crawl4ai_bill_exporter.py # 账单导出
│   └── web/
│       ├── app.py               # FastAPI 应用
│       ├── deps.py              # 共享依赖
│       ├── session_store.py     # 内存会话存储
│       ├── cookie_api.py        # Cookie 管理 API
│       ├── task_api.py          # 爬取任务 API
│       ├── clean_api.py         # 数据清洗 API
│       └── static/index.html    # React SPA
├── tests/
├── pyproject.toml
└── README.md
```

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /health | 健康检查 |
| POST | /api/cookies/upload | 上传 Cookie 文件 |
| GET | /api/cookies | 列出所有 Cookie |
| POST | /api/cookies/{id}/validate | 验证 Cookie |
| DELETE | /api/cookies/{id} | 删除 Cookie |
| POST | /api/qr-login/start | 启动扫码登录 |
| GET | /api/qr-login/{id}/stream | QR 登录 SSE 流 |
| POST | /api/crawl/start | 启动采集任务 |
| GET | /api/tasks/{id}/progress | 任务进度 SSE 流 |
| GET | /api/tasks/{id}/download/{idx} | 已禁用（未清洗数据不提供下载） |
| POST | /api/clean | 数据清洗 |
| POST | /api/clean/from-task/{id} | 从任务结果清洗 |
| POST | /api/clean/download | 下载清洗后的 JSON 结果 |

## 注意事项

1. 所有数据仅在内存中，服务重启后丢失，请及时下载
2. 最多同时运行 2 个浏览器实例
3. 请在安全的局域网环境中使用
4. 本工具仅供学习交流使用

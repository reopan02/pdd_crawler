# PDD Crawler - 拼多多商家后台数据采集工具

[![Python版本](https://img.shields.io/badge/Python-3.8%2B-blue)](https://www.python.org/)
[![项目版本](https://img.shields.io/badge/版本-0.1.0-green)](https://pypi.org/)

## 项目简介

PDD Crawler 是一个用于采集拼多多商家后台数据的 Python 爬虫工具。该工具可以自动化完成以下任务：

1. **用户认证** - 通过二维码登录拼多多商家后台，管理 Cookie 会话
2. **首页数据抓取** - 采集商家后台首页的店铺信息和经营数据
3. **账单导出** - 导出并下载商家的账单文件（支持 4001 和 4002 两种类型）

> **注意**：本工具仅供学习和研究使用，请遵守拼多多的服务条款和相关法律法规。

## 技术栈

- **Python 3.8+** - 编程语言
- **[crawl4ai](https://crawl4ai.com/)** - 异步 Web 爬虫框架
- **[Playwright](https://playwright.dev/python/)** - 浏览器自动化工具
- **pytest** - 测试框架

## 项目结构

```
pdd_crawler/
├── src/
│   └── pdd_crawler/
│       ├── __main__.py           # CLI 入口点
│       ├── config.py             # 配置和常量
│       ├── cookie_manager.py     # Cookie 管理与认证
│       ├── home_scraper.py       # 首页数据抓取
│       └── crawl4ai_bill_exporter.py  # 账单导出
├── tests/                        # 测试文件
├── cookies/                     # Cookie 存储目录
├── output/                      # 输出数据目录
├── docs/                        # 示例文档
├── pyproject.toml               # 项目配置
└── README.md                    # 项目文档
```

## 环境准备

### 1. 安装依赖

```bash
pip install -e .
```

或使用 poetry：

```bash
poetry install
```

### 2. 安装 Playwright 浏览器

```bash
playwright install chromium
```

## 使用方法

### 命令行接口

PDD Crawler 提供以下命令行选项：

```bash
# 查看帮助
pdd_crawler --help
```

#### 可用选项

| 选项 | 说明 |
|------|------|
| `--login` | 强制重新登录，刷新 Cookie |
| `--scrape-home` | 抓取商家后台首页数据 |
| `--export-bills` | 导出并下载账单文件 |
| `--all` | 执行完整流程（登录 → 抓取 → 导出） |
| `--shop-name` | 指定店铺名称（用于 Cookie 和输出目录命名） |

### 使用示例

#### 1. 完整流程（登录 + 抓取首页 + 导出账单）

```bash
pdd_crawler --all
```

#### 2. 仅登录（刷新 Cookie）

```bash
pdd_crawler --login
```

#### 3. 仅抓取首页数据

```bash
pdd_crawler --scrape-home
```

#### 4. 仅导出账单

```bash
pdd_crawler --export-bills
```

#### 5. 指定店铺名称

```bash
pdd_crawler --all --shop-name "我的店铺"
```

## 输出说明

### Cookie 存储

登录成功后，Cookie 会保存到 `cookies/{店铺名称}_cookies.json` 文件中。下次运行时可直接使用，无需重新登录。

### 数据输出

所有输出文件保存在 `output/{店铺名称}/` 目录下：

```
output/{店铺名称}/
├── home_data_*.json    # 首页抓取的 JSON 数据
├── bills_4001/         # 4001 类型账单文件
│   └── *.xlsx         # Excel 格式账单
└── bills_4002/         # 4002 类型账单文件
    └── *.xlsx         # Excel 格式账单
```

### 账单类型说明

| 账单类型 | 说明 |
|---------|------|
| 4001 | 资金流水账单 |
| 4002 | 订单交易账单 |

## 配置说明

### 配置文件

主要配置位于 [src/pdd_crawler/config.py](file:///e:/code/crawler/src/pdd_crawler/config.py)：

```python
# 超时配置（毫秒）
QR_LOGIN_TIMEOUT = 120          # 二维码登录超时（秒）
PAGE_LOAD_TIMEOUT = 30000       # 页面加载超时
DOWNLOAD_TIMEOUT = 60000        # 文件下载超时
COOKIE_VALIDATE_TIMEOUT = 15000 # Cookie 验证超时

# 浏览器配置
BROWSER_CONFIG = {
    "browser_type": "chromium",
    "headless": True,           # 无头模式
    "enable_stealth": True,     # 隐身模式
    "viewport_width": 1920,
    "viewport_height": 1080,
    # ...
}
```

### 反爬虫机制

工具内置了以下反检测特性：

1. **Stealth 模式** - 隐藏自动化特征
2. **自定义 User-Agent** - 模拟真实浏览器
3. **反检测脚本** - 移除 `navigator.webdriver` 等自动化标识
4. **随机延迟** - 避免请求过快被检测

## 常见问题

### Q: 登录失败怎么办？

1. 确保网络可以正常访问拼多多商家后台
2. 尝试删除 `cookies/` 目录下的旧 Cookie 文件后重新登录
3. 检查是否开启了 VPN 或代理，可能导致 IP 被风控

### Q: 账单导出失败怎么办？

1. 确认 Cookie 是否有效（尝试重新登录）
2. 检查输出目录是否有写入权限
3. 某些账单可能需要等待生成，可稍后重试

### Q: 如何查看详细日志？

目前程序会在控制台输出详细进度信息，包括：
- 认证流程状态
- 页面抓取进度
- 文件下载状态

### Q: 支持哪些账单类型？

目前支持两种账单类型：
- **4001**: 资金流水账单
- **4002**: 订单交易账单

## 开发指南

### 运行测试

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_cookie_manager.py

# 运行冒烟测试
pytest tests/test_smoke.py -v
```

### 代码规范

项目使用以下工具进行代码检查：

```bash
# 代码格式化
black .

# 类型检查
mypy src/

# 代码风格检查
flake8 src/
```

## 注意事项

1. **安全风险**：请妥善保管 Cookie 文件，不要提交到公开仓库
2. **频率限制**：避免过于频繁地访问拼多多后台，以免触发风控
3. **数据用途**：请仅将采集的数据用于合法用途
4. **责任声明**：使用本工具产生的任何问题由使用者自行承担

## 依赖版本

核心依赖：
- `crawl4ai >= 0.7.0`
- `playwright >= 1.40`
- `pytest >= 7.0`

详细依赖请参阅 [pyproject.toml](file:///e:/code/crawler/pyproject.toml)。

## 许可证

本项目仅供学习交流使用。

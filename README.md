# PDD Crawler (拼多多商家后台爬虫)

基于 Playwright 的拼多多商家后台自动化数据采集工具，支持 Cookie 持久化、二维码登录、首页数据抓取和账单导出下载。

## 功能特性

- 🔐 **Cookie 持久化管理** - 自动保存/加载登录状态，支持有效性检测
- 📱 **二维码登录** - Cookie 失效时自动弹出二维码供用户扫描登录
- 📊 **首页数据抓取** - 提取商家后台首页仪表盘数据，保存为 JSON 格式
- 📁 **账单导出下载** - 自动导出 cashier 账单中心两个 Tab 的账单文件
- 🛡️ **反爬虫对抗** - 内置浏览器指纹伪装，绕过 PDD 反爬检测
- 🖥️ **命令行工具** - 简洁的 CLI 接口，支持按需执行各项操作

## 环境要求

- Python 3.8+
- Google Chrome 浏览器（已安装）

## 安装

### 1. 克隆项目

```bash
git clone <repository-url>
cd crawler
```

### 2. 安装依赖

```bash
pip install -e .
```

### 3. 安装浏览器

```bash
playwright install chromium chrome
```

## 使用方法

### 命令行接口

```bash
python -m pdd_crawler [选项]
```

### 可用选项

| 选项 | 说明 |
|------|------|
| `--login` | 强制重新登录，刷新 Cookie |
| `--scrape-home` | 抓取商家后台首页数据 |
| `--export-bills` | 导出并下载账单文件 |
| `--all` | 执行完整流程（登录 → 抓取 → 导出） |

### 使用示例

#### 首次运行（完整流程）

```bash
python -m pdd_crawler --all
```

程序会：
1. 检查 Cookie 是否有效
2. 如果 Cookie 无效，弹出浏览器窗口显示二维码供扫描登录
3. 抓取首页数据并保存到 `output/home_data_YYYYMMDD_HHMMSS.json`
4. 导出两个 Tab 的账单文件到 `downloads/` 目录

#### 仅抓取首页数据

```bash
python -m pdd_crawler --scrape-home
```

#### 仅导出账单

```bash
python -m pdd_crawler --export-bills
```

#### 重新登录

```bash
python -m pdd_crawler --login
```

## 项目结构

```
crawler/
├── src/pdd_crawler/
│   ├── __init__.py          # 包初始化
│   ├── __main__.py          # CLI 入口点
│   ├── config.py            # 配置常量（URL、超时等）
│   ├── cookie_manager.py    # Cookie 管理（加载/验证/二维码登录）
│   ├── home_scraper.py      # 首页数据抓取
│   └── bill_exporter.py     # 账单导出下载
├── tests/
│   ├── __init__.py
│   └── test_smoke.py        # 烟雾测试
├── cookies/                  # Cookie 存储目录
│   └── pdd_cookies.json     # 登录状态文件
├── downloads/                # 下载的账单文件
├── output/                   # 抓取的数据输出
├── pyproject.toml           # 项目配置
└── README.md
```

## 工作原理

### 1. 认证流程

```
┌─────────────────┐
│  加载 Cookie    │
└────────┬────────┘
         │
    Cookie 存在？
         │
    ┌────┴────┐
    │ 是      │ 否
    ▼         ▼
┌─────────┐  ┌──────────────┐
│ 验证    │  │ 二维码登录   │
└────┬────┘  └──────┬───────┘
     │              │
  验证通过？     扫码成功
     │              │
  ┌──┴──┐          │
  │是   │否        │
  ▼     ▼          │
完成   二维码登录 ◄─┘
```

### 2. 反爬虫策略

程序采用多层反爬虫对抗措施：

- **浏览器伪装**：禁用 `AutomationControlled` 特征
- **指纹伪造**：覆盖 `navigator.webdriver`、`plugins`、`languages`
- **自然导航**：通过 mms.pinduoduo.com 侧边栏跳转 cashier，避免直接访问触反爬
- **真实 Chrome**：使用 `channel="chrome"` 调用已安装的 Chrome 浏览器

### 3. 账单导出流程

```
mms首页 → 点击"账房"侧边栏 → cashier账单页
    ↓
点击"导出账单" → 确认弹窗
    ↓
跳转到 export-history 页面
    ↓
点击"下载" → 保存文件
```

## 配置说明

主要配置项位于 `src/pdd_crawler/config.py`：

### 超时设置

| 常量 | 默认值 | 说明 |
|------|--------|------|
| `QR_LOGIN_TIMEOUT` | 120 秒 | 二维码登录超时时间 |
| `PAGE_LOAD_TIMEOUT` | 30000 毫秒 | 页面加载超时 |
| `DOWNLOAD_TIMEOUT` | 60000 毫秒 | 文件下载超时 |
| `COOKIE_VALIDATE_TIMEOUT` | 15000 毫秒 | Cookie 验证超时 |

### 目标 URL

| 常量 | URL |
|------|-----|
| `PDD_HOME_URL` | `https://mms.pinduoduo.com/home/` |
| `CASHIER_BILL_4001_URL` | `https://cashier.pinduoduo.com/main/bills?tab=4001&__app_code=113` |
| `CASHIER_BILL_4002_URL` | `https://cashier.pinduoduo.com/main/bills?tab=4002&__app_code=113` |

## 输出文件

### Cookie 文件

- **位置**: `cookies/pdd_cookies.json`
- **格式**: Playwright `storage_state` 格式（包含 cookies + localStorage）

### 首页数据

- **位置**: `output/home_data_YYYYMMDD_HHMMSS.json`
- **格式**:
```json
{
  "scraped_at": "2026-03-09T12:00:00",
  "url": "https://mms.pinduoduo.com/home/",
  "page_title": "拼多多商家后台",
  "data": {
    "item_0": "今日订单 1234",
    "item_1": "今日销售额 ¥56,789.00",
    ...
  }
}
```

### 账单文件

- **位置**: `downloads/`
- **格式**: CSV（PDD 导出的原始格式）

## 故障排除

### 问题：二维码登录超时

**原因**: 120 秒内未完成扫码

**解决**: 
- 确保拼多多商家 APP 已登录
- 在超时时间内完成扫码
- 如需更长时间，修改 `config.QR_LOGIN_TIMEOUT`

### 问题：Cookie 验证失败

**原因**: Cookie 过期或被服务器撤销

**解决**:
```bash
# 删除旧 Cookie 重新登录
rm cookies/pdd_cookies.json
python -m pdd_crawler --login
```

### 问题：反爬虫机制触发

**现象**: 显示"登录异常，请关闭页面后重试"

**解决**:
1. 删除 Cookie 重新登录
2. 确保使用真实 Chrome 浏览器（非 Chromium）
3. 检查 Chrome 版本是否过旧

### 问题：未找到导出按钮

**原因**: 页面结构变化或加载不完全

**解决**:
- 查看调试截图（如有）
- 增加页面等待时间
- 手动检查页面元素

## 开发

### 运行测试

```bash
python -m pytest tests/test_smoke.py -v
```

### 代码风格

```bash
# 格式化
black src/

# 检查
flake8 src/
```

## 注意事项

⚠️ **重要提示**

- 本工具仅供学习和个人使用
- 请遵守拼多多平台的用户协议和 `robots.txt` 规则
- 频繁请求可能导致账号被限制
- 不要将抓取的数据用于商业用途

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！
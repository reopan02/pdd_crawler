# PDD Crawler (拼多多商家后台爬虫)

基于 Playwright 的拼多多商家后台自动化数据采集工具，支持 Cookie 持久化、二维码登录、首页数据抓取和账单导出下载。

## 功能特性

- 🔐 **Cookie 持久化管理** - 自动保存/加载登录状态，支持有效性检测
- 📱 **二维码登录** - Cookie 失效时自动弹出二维码供用户扫描登录
- 🏪 **多店铺支持** - Cookie 和输出文件按店铺名称自动命名和分类
- 📊 **首页数据抓取** - 提取商家后台首页仪表盘数据，保存为 JSON 格式
- 📁 **账单导出下载** - 自动导出 cashier 账单中心两个 Tab 的账单文件
- 📦 **自动解压** - 下载的压缩包自动解压为 CSV 并删除原压缩包
- 🛡️ **反爬虫对抗** - 内置浏览器指纹伪装，绕过 PDD 反爬检测
- 🖥️ **命令行工具** - 简洁的 CLI 接口，支持按需执行各项操作

## 环境要求

- Python 3.8+
- Google Chrome 浏览器（已安装）

## 安装

### 1. 克隆项目

```bash
git clone https://github.com/reopan02/pdd_crawler.git
cd pdd_crawler
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
| `--shop-name NAME` | 指定店铺名称（默认自动提取） |

### 使用示例

#### 首次运行（完整流程）

```bash
python -m pdd_crawler --all
```

程序会：
1. 检查 Cookie 是否有效
2. 如果 Cookie 无效，弹出浏览器窗口显示二维码供扫描登录
3. 自动提取店铺名称
4. 抓取首页数据并保存到 `output/{店铺名称}/home_data_YYYYMMDD_HHMMSS.json`
5. 导出两个 Tab 的账单文件到 `output/{店铺名称}/` 目录
6. 如果下载的是 ZIP 文件，自动解压为 CSV 并删除 ZIP

#### 指定店铺名称

```bash
python -m pdd_crawler --all --shop-name "我的店铺"
```

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
pdd_crawler/
├── src/pdd_crawler/
│   ├── __init__.py          # 包初始化
│   ├── __main__.py          # CLI 入口点
│   ├── config.py            # 配置常量和辅助函数
│   ├── cookie_manager.py    # Cookie 管理（加载/验证/二维码登录）
│   ├── home_scraper.py      # 首页数据抓取和店铺名称提取
│   └── bill_exporter.py     # 账单导出、下载、解压
├── tests/
│   ├── __init__.py
│   └── test_smoke.py        # 烟雾测试
├── cookies/                  # Cookie 存储目录
│   └── {店铺名称}_cookies.json  # 按店铺命名的登录状态文件
├── output/                   # 所有输出文件的根目录
│   └── {店铺名称}/           # 按店铺分类的输出目录
│       ├── home_data_*.json  # 首页数据
│       └── bill_*.csv        # 账单文件（已解压）
├── pyproject.toml           # 项目配置
└── README.md
```

## 文件命名规则

### Cookie 文件

- **位置**: `cookies/{店铺名称}_cookies.json`
- **示例**: `cookies/测试店铺_cookies.json`
- **格式**: Playwright `storage_state` 格式（包含 cookies + localStorage）

### 输出文件

所有输出文件统一保存在 `output/{店铺名称}/` 目录下：

- **首页数据**: `output/{店铺名称}/home_data_YYYYMMDD_HHMMSS.json`
- **账单文件**: `output/{店铺名称}/bill_*.csv`（自动从 ZIP 解压）

### 示例输出结构

```
output/
└── 我的拼多多店铺/
    ├── home_data_20260309_120000.json
    ├── bill_4001_20260309_120500.csv
    └── bill_4002_20260309_121000.csv
```

## 工作原理

### 1. 认证流程

```
┌─────────────────┐
│  加载 Cookie    │ ← cookies/{店铺名称}_cookies.json
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
         │
         ▼
   保存 Cookie → cookies/{店铺名称}_cookies.json
```

### 2. 店铺名称提取

程序自动从商家后台首页提取店铺名称，用于：
- Cookie 文件命名
- 输出目录命名

如果无法自动提取，会使用时间戳作为默认名称。

### 3. 账单导出流程

```
mms首页 → 点击"账房"侧边栏 → cashier账单页
    ↓
点击"导出账单" → 确认弹窗
    ↓
跳转到 export-history 页面
    ↓
点击"下载" → 保存文件
    ↓
如果 ZIP → 自动解压为 CSV → 删除 ZIP
```

### 4. 反爬虫策略

程序采用多层反爬虫对抗措施：

- **浏览器伪装**：禁用 `AutomationControlled` 特征
- **指纹伪造**：覆盖 `navigator.webdriver`、`plugins`、`languages`、Chrome 对象
- **自然导航**：通过 mms.pinduoduo.com 侧边栏跳转 cashier，避免直接访问触反爬
- **真实 Chrome**：使用 `channel="chrome"` 调用已安装的 Chrome 浏览器

## 配置说明

主要配置项位于 `src/pdd_crawler/config.py`：

### 超时设置

| 常量 | 默认值 | 说明 |
|------|--------|------|
| `QR_LOGIN_TIMEOUT` | 120 秒 | 二维码登录超时时间 |
| `PAGE_LOAD_TIMEOUT` | 30000 毫秒 | 页面加载超时 |
| `DOWNLOAD_TIMEOUT` | 60000 毫秒 | 文件下载超时 |
| `COOKIE_VALIDATE_TIMEOUT` | 15000 毫秒 | Cookie 验证超时 |

### 目录配置

| 函数 | 说明 |
|------|------|
| `get_cookie_path(shop_name)` | 获取指定店铺的 Cookie 文件路径 |
| `get_shop_output_dir(shop_name)` | 获取指定店铺的输出目录 |

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
rm cookies/{店铺名称}_cookies.json
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
# INTEGRATIONS — External Services

## Pinduoduo (拼多多) — Target Platform

### Services

| Service | URL | Purpose |
|---------|-----|---------|
| Merchant后台 (MMS) | `https://mms.pinduoduo.com` | 商家管理后台 - 首页数据抓取 |
| 收银台 (Cashier) | `https://cashier.pinduoduo.com` | 资金流水、订单交易账单导出 |
| 登录页 | `https://mms.pinduoduo.com/login` | Cookie有效性检测 |

### Authentication Flow
1. **Cookie上传** — 用户上传 Playwright `storage_state` JSON
2. **QR登录** — 启动非无头浏览器，用户扫码登录拼多多APP
3. **SSO跳转** — 从MMS跳转到Cashier时自动携带认证ticket

### Bill Export Endpoints
```
# 资金流水 (tab 4001)
https://cashier.pinduoduo.com/main/bills?tab=4001&__app_code=113

# 订单交易 (tab 4002)  
https://cashier.pinduoduo.com/main/bills?tab=4002&__app_code=113
```

### Export History Pages
```
# 查询已导出的文件
https://cashier.pinduoduo.com/main/bills/export-history?tab=4001&__app_code=113
https://cashier.pinduoduo.com/main/bills/export-history?tab=4002&__app_code=113
```

## No External Database

- All data stored in-memory (SessionStore)
- No persistent storage (except optional cookie files)
- Data lost on server restart

## No External API Integrations

- No third-party authentication providers
- No webhook integrations
- No cloud storage (data served directly to browser)

## Browser Integration

- **Playwright** directly via crawl4ai
- Chromium browser only
- Stealth mode enabled (anti-bot detection)
- Download directory: configurable, defaults to temp

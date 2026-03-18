# CONCERNS — Technical Debt & Issues

## Known Issues

### 1. Type Errors in Core Modules

**Files**: `cookie_manager.py`, `home_scraper.py`

The code uses internal crawl4ai APIs that lack type stubs:
```
ERROR: Cannot access attribute "browser_manager" for class "AsyncCrawlerStrategy"
ERROR: Cannot access attribute "logger" for class "AsyncCrawlerStrategy"
```

**Status**: Mitigated with pyright per-file disables, but indicates fragile coupling to internal APIs.

### 2. Memory-Only Data Persistence

**Issue**: All data stored in `SessionStore` (in-memory). Server restart = data loss.

**Impact**: Users must re-upload cookies and re-download results before restart.

**Status**: By design (security), but no warning system.

### 3. No Authentication

**Issue**: API has no auth. CORS allows all origins.

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # No restriction
)
```

**Impact**: Anyone on network can access API.

**Status**: Documented in README as "安全环境" requirement.

### 4. Browser Concurrency Limits

**Issue**: Hardcoded `Semaphore(2)` limits simultaneous browsers.

```python
# From deps.py - exact value not in codebase analysis
semaphore = asyncio.Semaphore(2)
```

**Impact**: Cannot scale to >2 concurrent crawls.

**Status**: No configuration option.

### 5. No Rate Limiting

**Issue**: No request throttling to PDD.

**Impact**: Risk of account ban from rapid scraping.

**Status**: Documented in README: "频率控制 — 避免过于频繁"

### 6. Weak Error Handling

**Issue**: Generic exception catching in some places:

```python
try:
    ...
except Exception as e:
    print(f"[Cookie] 验证失败: {e}")
    return False
```

**Impact**: Swallows real errors, hard to debug.

### 7. Test Gaps

- No API endpoint tests
- No mocking (integration only)
- No session isolation verification

### 8. Frontend Not Built

**Issue**: `static/index.html` mentioned but not analyzed.

**Status**: README says "React SPA (内嵌 static/index.html)", but HTML may be placeholder.

## Security Considerations

| Concern | Risk | Mitigation |
|---------|------|------------|
| No API auth | High | LAN-only use |
| Cookie in memory | Medium | Session-based |
| No HTTPS enforced | Medium | Documentation |

## Fragile Areas

1. **`cookie_manager.py`**: Direct access to crawl4ai internals
2. **`home_scraper.py`**: CSS selector scraping (fragile to UI changes)
3. **Bill export**: SSO flow dependent on PDD not changing endpoints

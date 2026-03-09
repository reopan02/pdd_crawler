"""Main entry point for PDD crawler."""

import argparse
import asyncio
import sys

from pdd_crawler.config import (
    COOKIES_DIR,
    OUTPUT_BASE_DIR,
    get_cookie_path,
    get_shop_output_dir,
)
from pdd_crawler.cookie_manager import ensure_authenticated
from pdd_crawler.home_scraper import run_home_scraper
from pdd_crawler.bill_exporter import export_all_bills


async def main() -> None:
    """Main function with CLI routing."""
    parser = argparse.ArgumentParser(
        description="PDD Crawler - 拼多多商家后台数据采集工具"
    )
    parser.add_argument(
        "--login", action="store_true", help="强制重新登录，刷新 Cookie"
    )
    parser.add_argument(
        "--scrape-home", action="store_true", help="抓取商家后台首页数据"
    )
    parser.add_argument(
        "--export-bills", action="store_true", help="导出并下载账单文件"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="执行完整流程（登录 → 抓取 → 导出）",
    )
    parser.add_argument(
        "--shop-name",
        type=str,
        default=None,
        help="店铺名称（用于 Cookie 和输出目录命名，默认自动提取）",
    )

    args = parser.parse_args()

    # Ensure required directories exist
    COOKIES_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_BASE_DIR.mkdir(parents=True, exist_ok=True)

    # Default to --all if no arguments provided
    if not any([args.login, args.scrape_home, args.export_bills, args.all]):
        args.all = True

    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            context = None
            browser = None
            shop_name = args.shop_name

            try:
                # Step 1: Authenticate
                if args.login or args.scrape_home or args.export_bills or args.all:
                    print("=" * 50)
                    print("开始认证流程...")
                    print("=" * 50)
                    context, browser, shop_name = await ensure_authenticated(
                        p, shop_name
                    )
                    print(f"✓ 认证完成 (店铺: {shop_name})")

                    # Get shop-specific output directory
                    output_dir = get_shop_output_dir(shop_name)
                    output_dir.mkdir(parents=True, exist_ok=True)
                    print(f"输出目录: {output_dir}")

                # Use a single page across operations
                page = await context.new_page()

                try:
                    # Step 2: Scrape home page if requested
                    if args.scrape_home or args.all:
                        print("\n" + "=" * 50)
                        print("抓取首页数据...")
                        print("=" * 50)
                        _, home_file = await run_home_scraper(page, output_dir)
                        print(f"✓ 首页数据抓取完成: {home_file}")

                    # Step 3: Export bills if requested
                    if args.export_bills or args.all:
                        print("\n" + "=" * 50)
                        print("导出账单...")
                        print("=" * 50)
                        downloaded = await export_all_bills(context, page, output_dir)
                        print(f"✓ 账单导出完成，共 {len(downloaded)} 个文件")

                finally:
                    await page.close()

            except KeyboardInterrupt:
                print("\n✗ 用户取消操作")
                sys.exit(1)
            finally:
                if context is not None:
                    await context.close()
                if browser is not None:
                    await browser.close()

    except ImportError as e:
        print(f"错误: 缺少依赖 - {e}")
        print("请运行: pip install -e . && playwright install chromium chrome")
        sys.exit(1)
    except Exception as e:
        print(f"错误: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

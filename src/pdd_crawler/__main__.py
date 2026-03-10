"""Main entry point for PDD crawler."""

import argparse
import asyncio
import sys
import uuid

from pdd_crawler.config import (
    COOKIES_DIR,
    OUTPUT_BASE_DIR,
    get_shop_output_dir,
)
from pdd_crawler.cookie_manager import ensure_authenticated, create_crawler
from pdd_crawler.home_scraper import run_home_scraper
from pdd_crawler.crawl4ai_bill_exporter import export_all_bills


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
        # ── Step 1: Authenticate ──
        # ensure_authenticated validates/refreshes cookies and closes
        # its browser before returning. We get back a cookie file path
        # and the real shop name.
        if args.login or args.scrape_home or args.export_bills or args.all:
            print("=" * 50)
            print("开始认证流程...")
            print("=" * 50)
            cookie_path, shop_name = await ensure_authenticated(args.shop_name)
            print(f"✓ 认证完成 (店铺: {shop_name})")

            # Prepare shop-specific output directory
            output_dir = get_shop_output_dir(shop_name)
            output_dir.mkdir(parents=True, exist_ok=True)
            print(f"输出目录: {output_dir}")
        else:
            return

        # If only --login was requested, we're done
        if args.login and not (args.scrape_home or args.export_bills or args.all):
            print("✓ 登录完成，Cookie 已保存")
            return

        # ── Step 2: Create crawler session for home scraping and/or bill export ──
        if args.scrape_home or args.export_bills or args.all:
            session_id = str(uuid.uuid4())
            crawler = await create_crawler(cookie_path=cookie_path, headless=True, downloads_path=output_dir)
            
            try:
                # Step 2a: Home scraping (if requested)
                if args.scrape_home or args.all:
                    try:
                        print("\n" + "=" * 50)
                        print("抓取首页数据...")
                        print("=" * 50)
                        _, home_file = await run_home_scraper(crawler, session_id, output_dir)
                        print(f"✓ 首页数据抓取完成: {home_file}")

                    except KeyboardInterrupt:
                        print("\n✗ 用户取消操作")
                        sys.exit(1)

                # Step 2b: Bill export (if requested)
                if args.export_bills or args.all:
                    print("\n" + "=" * 50)
                    print("导出账单...")
                    print("=" * 50)
                    downloaded = await export_all_bills(crawler, session_id, cookie_path, output_dir)
                    print(f"✓ 账单导出完成，共 {len(downloaded)} 个文件")

            except KeyboardInterrupt:
                print("\n✗ 用户取消操作")
                sys.exit(1)
            finally:
                await crawler.close()

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

"""Main entry point for PDD crawler."""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

from pdd_crawler.config import (
    COOKIES_DIR,
    OUTPUT_BASE_DIR,
    get_shop_output_dir,
)
from pdd_crawler.cookie_manager import (
    create_crawler,
    list_all_cookies,
    qr_login,
    validate_cookies,
)
from pdd_crawler.home_scraper import run_home_scraper
from pdd_crawler.crawl4ai_bill_exporter import export_all_bills


async def _run_pipeline_for_shop(
    cookie_path: Path,
    shop_name: str,
    *,
    scrape_home: bool,
    export_bills: bool,
) -> None:
    """Run scrape/export pipeline for a single shop."""
    output_dir = get_shop_output_dir(shop_name)
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"输出目录: {output_dir}")

    session_id = str(uuid.uuid4())
    crawler = await create_crawler(
        cookie_path=cookie_path, headless=True, downloads_path=output_dir,
    )

    try:
        if scrape_home:
            try:
                print("\n" + "=" * 50)
                print(f"抓取首页数据 (店铺: {shop_name})...")
                print("=" * 50)
                _, home_file = await run_home_scraper(crawler, session_id, output_dir)
                print(f"✓ 首页数据抓取完成: {home_file}")
            except KeyboardInterrupt:
                print("\n✗ 用户取消操作")
                sys.exit(1)

        if export_bills:
            print("\n" + "=" * 50)
            print(f"导出账单 (店铺: {shop_name})...")
            print("=" * 50)
            downloaded = await export_all_bills(
                crawler, session_id, cookie_path, output_dir,
            )
            print(f"✓ 账单导出完成，共 {len(downloaded)} 个文件")

    except KeyboardInterrupt:
        print("\n✗ 用户取消操作")
        sys.exit(1)
    finally:
        await crawler.close()


async def main() -> None:
    """Main function with CLI routing."""
    parser = argparse.ArgumentParser(
        description="PDD Crawler - 拼多多商家后台数据采集工具"
    )
    parser.add_argument(
        "--login", action="store_true", help="扫码登录并添加 Cookie"
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
        help="遍历所有已有 Cookie，对每个店铺执行抓取+导出",
    )
    parser.add_argument(
        "--shop-name",
        type=str,
        default=None,
        help="指定店铺名称（用于 --login 命名或 --scrape-home/--export-bills 选择店铺）",
    )

    args = parser.parse_args()

    # Ensure required directories exist
    COOKIES_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_BASE_DIR.mkdir(parents=True, exist_ok=True)

    # Default to --all if no arguments provided
    if not any([args.login, args.scrape_home, args.export_bills, args.all]):
        args.all = True

    try:
        # ── --login: QR login to add a new cookie ──
        if args.login:
            print("=" * 50)
            print("扫码登录，添加 Cookie...")
            print("=" * 50)
            cookie_path, shop_name = await qr_login(shop_name=args.shop_name)
            print(f"✓ 登录完成，Cookie 已保存 (店铺: {shop_name})")
            print(f"  文件: {cookie_path}")

            # If only --login, stop here
            if not (args.scrape_home or args.export_bills or args.all):
                return

        # ── --all: iterate ALL existing cookies ──
        if args.all:
            all_cookies = list_all_cookies()
            if not all_cookies:
                print("未找到任何已保存的 Cookie，请先使用 --login 添加")
                print("  用法: python -m pdd_crawler --login")
                sys.exit(1)

            print("=" * 50)
            print(f"找到 {len(all_cookies)} 个已保存的 Cookie:")
            for i, (cp, name) in enumerate(all_cookies, 1):
                print(f"  {i}. {name} ({cp.name})")
            print("=" * 50)

            for i, (cookie_path, shop_name) in enumerate(all_cookies, 1):
                print(f"\n{'=' * 50}")
                print(f"[{i}/{len(all_cookies)}] 处理店铺: {shop_name}")
                print("=" * 50)

                # Validate cookie before running pipeline
                if not await validate_cookies(cookie_path):
                    print(f"⚠ 跳过 {shop_name}: Cookie 已失效，请使用 --login 重新登录")
                    continue

                await _run_pipeline_for_shop(
                    cookie_path,
                    shop_name,
                    scrape_home=True,
                    export_bills=True,
                )

            print(f"\n{'=' * 50}")
            print(f"✓ 全部完成，共处理 {len(all_cookies)} 个店铺")
            print("=" * 50)
            return

        # ── --scrape-home / --export-bills for a single shop ──
        if args.scrape_home or args.export_bills:
            # Find the cookie to use
            if args.shop_name:
                from pdd_crawler.config import get_cookie_path

                cookie_path = get_cookie_path(args.shop_name)
                shop_name = args.shop_name
                if not cookie_path.exists():
                    print(f"未找到店铺 '{shop_name}' 的 Cookie 文件: {cookie_path}")
                    print("请先使用 --login 添加")
                    sys.exit(1)
            else:
                # Use first valid cookie
                all_cookies = list_all_cookies()
                if not all_cookies:
                    print("未找到任何已保存的 Cookie，请先使用 --login 添加")
                    sys.exit(1)
                cookie_path, shop_name = all_cookies[0]

            if not await validate_cookies(cookie_path):
                print(f"Cookie 已失效 (店铺: {shop_name})，请使用 --login 重新登录")
                sys.exit(1)

            print(f"✓ 使用 Cookie: {shop_name}")
            await _run_pipeline_for_shop(
                cookie_path,
                shop_name,
                scrape_home=args.scrape_home,
                export_bills=args.export_bills,
            )

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

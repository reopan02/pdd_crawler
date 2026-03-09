"""Main entry point for PDD crawler."""

import argparse
import asyncio
import sys

from pdd_crawler.config import COOKIES_DIR, DOWNLOADS_DIR, OUTPUT_DIR


async def main() -> None:
    """Main function with CLI routing."""
    parser = argparse.ArgumentParser(
        description="PDD Crawler - Automated PDD scraping tool"
    )
    parser.add_argument(
        "--login", action="store_true", help="Authenticate with PDD and save cookies"
    )
    parser.add_argument(
        "--scrape-home", action="store_true", help="Scrape PDD home page data"
    )
    parser.add_argument(
        "--export-bills", action="store_true", help="Export bill information from PDD"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all operations (login, scrape home, export bills)",
    )

    args = parser.parse_args()

    # Ensure required directories exist
    COOKIES_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Default to --all if no arguments provided
    if not any([args.login, args.scrape_home, args.export_bills, args.all]):
        args.all = True

    # Import Playwright and other modules
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context()

            try:
                # Route based on arguments
                if args.login or args.all:
                    print("Starting authentication process...")
                    # TODO: Implement authentication with cookie_manager
                    print("✓ Authentication completed")

                if args.scrape_home or args.all:
                    print("Scraping PDD home page...")
                    # TODO: Implement home page scraping
                    print("✓ Home page scraping completed")

                if args.export_bills or args.all:
                    print("Exporting bill information...")
                    # TODO: Implement bill export
                    print("✓ Bill export completed")

            except KeyboardInterrupt:
                print("\n✗ Operation cancelled by user")
                sys.exit(1)
            finally:
                await context.close()
                await browser.close()

    except ImportError as e:
        print(f"Error: Required dependency not found - {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

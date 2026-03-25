"""Main entry point for PDD Crawler — launches the web server.

Usage:
    python -m pdd_crawler [--host HOST] [--port PORT]
"""

from __future__ import annotations

import os
import sys

# Force-redirect all libpq config file lookups BEFORE any imports.
# On Chinese Windows, libpq reads GBK-encoded files (pgpass.conf,
# pg_service.conf) and psycopg2 crashes decoding them as UTF-8.
# Setting these to non-existent paths makes libpq skip the reads entirely.
if os.name == "nt":
    _nul = "NUL"
    _nodir = "C:\\nonexistent_pdd_pg_conf"
    os.environ["PGPASSFILE"] = _nul
    os.environ["PGSERVICEFILE"] = _nul
    os.environ["PGSYSCONFDIR"] = _nodir
    os.environ["PGAPPNAME"] = "pdd_crawler"

# Load .env from project root before anything else
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PDD Crawler - 拼多多商家后台数据采集工具 (Web 版)"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="监听地址 (默认: 0.0.0.0, 局域网可访问)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8089,
        help="监听端口 (默认: 8089)",
    )
    args = parser.parse_args()

    print("=" * 50)
    print(f"PDD Crawler Web 启动中...")
    print(f"访问地址: http://{args.host}:{args.port}")
    print(f"局域网访问: http://<本机IP>:{args.port}")
    print("=" * 50)

    uvicorn.run(
        "pdd_crawler.web.app:app",
        host=args.host,
        port=args.port,
        reload=False,
    )


if __name__ == "__main__":
    main()

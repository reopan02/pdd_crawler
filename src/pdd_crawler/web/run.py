"""Web server entry point.

Usage:
    python -m pdd_crawler.web.run
    # or via installed script:
    pdd_web
"""

import uvicorn


def main():
    uvicorn.run(
        "pdd_crawler.web.app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    main()

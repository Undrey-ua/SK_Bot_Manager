from __future__ import annotations

import logging
import os
import sys

import uvicorn

from config.settings import get_settings
from utils.logging import setup_logging
from web.app import create_app

logger = logging.getLogger(__name__)


def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)

    if not settings.dashboard_password.strip():
        logger.error(
            "DASHBOARD_PASSWORD не задано. Додайте пароль у .env для веб-панелі."
        )
        sys.exit(1)

    app = create_app(settings)
    port = int(os.environ.get("PORT", str(settings.web_port)))
    logger.info("Web dashboard starting on port %s", port)
    # Railway proxy тримає keep-alive ~60 с; uvicorn за замовчуванням — 5 с → інколи 502/upstream error.
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
        timeout_keep_alive=65,
    )


if __name__ == "__main__":
    main()

from __future__ import annotations

import logging
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
    logger.info("Web dashboard starting on port %s", settings.web_port)
    uvicorn.run(app, host="0.0.0.0", port=settings.web_port, log_level="info")


if __name__ == "__main__":
    main()

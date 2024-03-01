import undetected_chromedriver as uc
import logging
from typing import Literal
from pydantic import BaseModel
from selenium.common.exceptions import InvalidArgumentException
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType


class Config(BaseModel):
    version: str = "0.1.0"
    browser: Literal["chrome", "chromium"] = "chrome"
    headless: bool = True
    username: str | None = None
    password: str | None = None
    viewer_size: tuple[int, int] = (960, 1360)
    user_agent: str | None = None
    logging_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    def get_webdriver(self):
        ua = self.user_agent or "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        options = uc.ChromeOptions()
        options.set_capability("unhandledPromptBehavior", "accept")
        options.add_argument("--high-dpi-support=1")
        options.add_argument("--device-scale-factor=1")
        options.add_argument("--force-device-scale-factor=1")
        options.add_argument(f"--user-agent={ua}")
        chrome_type = ChromeType.CHROMIUM if self.browser == "chromium" else ChromeType.GOOGLE
        chrome_driver = uc.Chrome(
            options=options,
            headless=self.headless,
            driver_executable_path=ChromeDriverManager(chrome_type=chrome_type).install())
        return chrome_driver

    def get_logger(self):
        level = getattr(logging, self.logging_level)
        logging.basicConfig(level=level)
        logger = logging.getLogger("bookphucker")
        return logger

from __future__ import annotations
import undetected_chromedriver as uc
import logging
from typing import Literal
from pydantic import BaseModel, ConfigDict
from semantic_version import Version
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType
from selenium.webdriver.chrome.service import Service


CURRENT_VERSION = Version("0.2.0")

class Config(BaseModel):
    model_config = ConfigDict(extra="allow", validate_assignment=True)
    version: str = str(CURRENT_VERSION)
    browser: Literal["chrome", "chromium"] = "chrome"
    headless: bool = True
    username: str | None = None
    password: str | None = None
    manual_login: bool = False
    viewer_size: tuple[int, int] = (1440, 1440)
    user_agent: str | None = None
    logging_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    def get_webdriver(self):
        ua = self.user_agent or "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        options = uc.ChromeOptions()
        options.set_capability("unhandledPromptBehavior", "accept")
        options.add_argument("--high-dpi-support=1")
        options.add_argument(f"--user-agent={ua}")
        options.add_argument(f"--window-size={self.viewer_size[0]},{self.viewer_size[1]}")
        # snap specific options to allow chromedriver to find browser
        #options.binary_location = "/usr/bin/chromium-browser"
        #options.add_argument("--no-sandbox")
        #options.add_argument("--disable-dev-shm-usage")

        chrome_type = ChromeType.CHROMIUM if self.browser == "chromium" else ChromeType.GOOGLE
        # Install matching ChromeDriver and create a Service
        service = Service(ChromeDriverManager(chrome_type=chrome_type).install())
        # Handle headless mode via options
        if self.headless:
            # use new headless flag for modern Chrome
            options.add_argument("--headless=new")
        # Initialize undetected_chromedriver with correct service
        driver = uc.Chrome(options=options, service=service)
        return driver

    def config_logging(self):
        level = getattr(logging, self.logging_level)
        logging.basicConfig(level=level)
    
    @classmethod
    def from_dict(cls, data: dict) -> tuple[Config, bool]:
        """
        # Recover Config object from dictionary
        also return if it was updated
        """
        if "version" not in data:
            raise ValueError("Version not found in data")
        data_version = Version(data.pop("version"))
        if (data_version.major, data_version.minor) == (CURRENT_VERSION.major, CURRENT_VERSION.minor):
            return Config(**data), data_version.patch < CURRENT_VERSION.patch
        if data_version.major > CURRENT_VERSION.major:
            raise ValueError("Unsupported config version")
        if data_version < Version("0.2.0"):
            data["viewer_size"] = cls.viewer_size
        return Config(**data), True
        

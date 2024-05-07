import ujson as json
from typing import Any
from selenium import webdriver
from urllib.parse import urlparse
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from .commonvars import cookies_path


def recover_cookies(driver: webdriver.Chrome, url: str) -> bool:
    if not cookies_path.exists():
        return False
    all_cookies: dict[str, list[dict[str, Any]]] = json.loads(cookies_path.read_text())
    netloc = urlparse(url).netloc
    if netloc not in all_cookies:
        return False
    driver.get(url)
    driver.delete_all_cookies()
    cookies = all_cookies[netloc]
    for cookie in cookies:
        driver.add_cookie(cookie)
    return True


def save_cookies(driver: webdriver.Chrome, url: str):
    driver.get(url)
    cookies = driver.get_cookies()
    if not cookies_path.exists():
        all_cookies = {}
    else:
        all_cookies = json.loads(cookies_path.read_text())
    netloc = urlparse(url).netloc
    all_cookies[netloc] = cookies
    cookies_path.write_text(json.dumps(all_cookies, indent=2))


def scroll_click(driver: webdriver.Chrome, element: WebElement, timeout: int = 10):
    WebDriverWait(driver, timeout).until(EC.element_to_be_clickable(element))
    webdriver.ActionChains(driver).scroll_to_element(element).perform()
    element.click()  # sending click event to element instead of clicking on element position with action chains


def find_click(driver: webdriver.Chrome, by: str, value: str, timeout: int = 10):
    element = driver.find_element(by, value)
    scroll_click(driver, element, timeout)

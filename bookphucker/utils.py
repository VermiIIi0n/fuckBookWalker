import ujson as json
from typing import Any
from selenium import webdriver
from selenium.webdriver.common.by import By
# from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from contextlib import suppress
from .commonvars import cookies_path, config_path, cache_path


def scroll_click(driver: webdriver.Chrome, element: WebElement, timeout: int = 10):
    WebDriverWait(driver, timeout).until(EC.element_to_be_clickable(element))
    webdriver.ActionChains(driver).scroll_to_element(element).perform()
    element.click()  # sending click event to element instead of clicking on element position with action chains


def find_click(driver: webdriver.Chrome, by: str, value: str, timeout: int = 10):
    element = driver.find_element(by, value)
    scroll_click(driver, element, timeout)

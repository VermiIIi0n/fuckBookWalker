import ujson as json
import bs4
import io
import logging
import time
from rich.progress import track
from typing import Any
from selenium import webdriver
from selenium.webdriver.common.by import By
# from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from time import sleep
from pathlib import Path
from bookphucker import Config
from contextlib import suppress
from PIL import Image
from base64 import b64decode
from collections import deque
from .exc import RequiresCapcha, Error998
from .commonvars import cookies_path, config_path, cache_path
from .utils import find_click, scroll_click

domain = "bookwalker.jp"


def recover_cookies(driver: webdriver.Chrome) -> bool:
    url = f"https://member.{domain}/app/03/my/profile"
    if not cookies_path.exists():
        return False
    cookies: list[dict[str, Any]] = json.loads(cookies_path.read_text())
    driver.get(url)
    driver.delete_all_cookies()
    for cookie in cookies:
        driver.add_cookie(cookie)

    driver.get(url)
    with suppress(TimeoutException):
        WebDriverWait(driver, 5).until(lambda x: "ES0001" in x.page_source)
        return False
    try:
        WebDriverWait(driver, 5).until(EC.url_to_be(url))
        return True
    except TimeoutException:
        return False


def login(driver: webdriver.Chrome, username: str, password: str, error_on_captcha=False):
    driver.delete_all_cookies()
    driver.get(f"https://{domain}/")
    # driver.find_element(By.CLASS_NAME, "bw_btn-login").click()
    # find_click(driver, By.CLASS_NAME, "bw_btn-login")
    driver.execute_script("sendGa(1,'グローバルナビ','クリック','ヘッダログイン');")
    driver.get(f"https://member.{domain}/app/03/webstore/cooperation?r=top%2F")
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "mailAddress")))

    driver.find_element(By.ID, "mailAddress").send_keys(username)
    driver.find_element(By.ID, "password").send_keys(password)

    try:
        # driver.find_element(By.ID, "loginBtn").click()
        find_click(driver, By.ID, "loginBtn", 1)
    except NoSuchElementException:
        # driver.find_element(By.ID, "recaptchaLoginBtn").click()
        find_click(driver, By.ID, "recaptchaLoginBtn")
        # check if google recaptcha iframe exists
        with suppress(TimeoutException):
            WebDriverWait(driver, 2).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, "iframe[src^='https://www.recaptcha.net/recaptcha/api2/bframe']")))
            if error_on_captcha:
                raise RequiresCapcha()

    while True:
        cookies = driver.get_cookies()
        if any(c["name"] == "bwmember" for c in cookies):
            cookies_path.write_text(json.dumps(cookies))
            break


def logout(driver: webdriver.Chrome):
    # driver.get(f"https://member.{domain}/app/03/my/profile")
    # driver.get(f"https://{domain}/")
    # find_click(driver, By.CLASS_NAME, "header-menu-item--mypage")
    driver.get(f"https://member.{domain}/app/03/my/profile")
    find_click(driver, By.CLASS_NAME, "l-header__logout")
    # driver.get(f"https://member.{domain}/app/03/logout")


def wait4loading(driver: webdriver.Chrome, timeout: int = 30):
    WebDriverWait(driver, timeout).until_not(
        lambda x: any(e.is_displayed() for e in x.find_elements(By.CLASS_NAME, "loading")))


def get_pages(driver: webdriver.Chrome, timeout: int = 10):
    begin = time.time()
    while True:
        page_counter = driver.find_element(By.ID, "pageSliderCounter")
        with suppress(ValueError):
            text = page_counter.get_attribute("innerText") or ''
            current_page, total_pages = map(int, text.split('/'))
            break
        if time.time() - begin > timeout:
            raise TimeoutException
    return current_page, total_pages


def get_menu_name(driver: webdriver.Chrome) -> str:
    obj_name = driver.execute_script(
        "for (let k in NFBR.a6G.Initializer){if (NFBR.a6G.Initializer[k]['menu'] !== undefined){ return k; }}")
    return f"NFBR.a6G.Initializer.{obj_name}.menu"


def go2page(driver: webdriver.Chrome, menu_name: str, page: int):
    driver.execute_script(f"{menu_name}.options.a6l.moveToPage({page-1});")


def download_book(driver: webdriver.Chrome, cfg: Config, book_uuid: str, logger: logging.Logger):
    logger.info("Downloading book %s", book_uuid)
    driver.get(f"https://{domain}/de{book_uuid}/")
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CLASS_NAME, "p-main__title")))

    soup = bs4.BeautifulSoup(driver.page_source, "lxml")

    title = soup.find(class_="p-main__title").text.strip()
    authors_ml = soup.find(class_="p-author").find_all("dd")
    authors = [a.text.strip() for a in authors_ml]

    logger.info("Titled %s by %s", title, ", ".join(authors))

    driver.set_window_size(*cfg.viewer_size)  # size of bw page

    with suppress(TimeoutException):
        WebDriverWait(driver, 3).until(EC.presence_of_element_located(
            (By.CLASS_NAME, "gdpr-accept"))
        )
        # driver.find_element(By.CLASS_NAME, "gdpr-accept").click()
        find_click(driver, By.CLASS_NAME, "gdpr-accept")

    driver.get(f"https://member.{domain}/app/03/webstore/cooperation"
               f"?r=BROWSER_VIEWER/{book_uuid}/https%3A%2F%2Fbookwalker.jp%2Fde{book_uuid}%2F")

    save_dir = Path(f"babies/{title}")
    save_dir.mkdir(exist_ok=True, parents=True)
    meta_path = save_dir / "meta.json"
    meta_path.write_text(json.dumps(
        {"title": title, "authors": authors},
        ensure_ascii=False, indent=2))

    driver.switch_to.window(driver.window_handles[-1])

    wait4loading(driver)

    with suppress(TimeoutException):
        WebDriverWait(driver, 10).until(EC.presence_of_element_located(
            (By.ID, "pageSliderCounter"))
        )

    if "ERROR998" in driver.page_source:
        logger.error("Error 998: Must log out from another device")
        raise Error998()

    _, total_pages = get_pages(driver)
    prev_imgs = deque[bytes](maxlen=2)  # used for checking update for 2 buffers
    max_retries = 30
    logger.info("Total pages: %s", total_pages)

    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, ".currentScreen canvas")))
    menu_name = get_menu_name(driver)

    WebDriverWait(driver, 30).until(
        EC.invisibility_of_element_located((By.CLASS_NAME, "progressbar")))

    go2page(driver, menu_name, 1)

    for current_page in track(range(1, total_pages + 1), description="Downloading", total=total_pages):
        retry = 0
        go2page(driver, menu_name, current_page)
        while current_page != get_pages(driver)[0]:
            sleep(0.1)
        wait4loading(driver)
        logger.debug("Getting page %s out of %s", current_page, total_pages)
        canvas = driver.find_element(By.CSS_SELECTOR, ".currentScreen canvas")
        # canvas_pt = webdriver.ActionChains(driver).move_to_element(canvas)
        while retry < max_retries:
            canvas_base64 = driver.execute_script(
                "return arguments[0].toDataURL('image/png').slice(21);", canvas)
            img_bytes = b64decode(canvas_base64)
            img = Image.open(io.BytesIO(img_bytes))
            if all(all(v == 0 for v in c) for c in img.getdata()):
                logger.debug("Blank page %s, treated as unloaded page", current_page)
            elif img_bytes not in prev_imgs:
                prev_imgs.append(img_bytes)
                break
            retry += 1
            logger.debug("Retrying page %s (%s/%s)", current_page, retry, max_retries)
            sleep(0.3)
        if retry == max_retries:
            logger.warning("Potentially repeated page %s", current_page)
        img.save(save_dir / f"page_{current_page}.png")
        logger.debug("Saved page %s", current_page)
        # canvas_pt.send_keys(Keys.ARROW_LEFT).perform()

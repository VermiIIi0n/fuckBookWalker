import ujson as json
import bs4
import io
import logging
import time
from typing import cast
from rich.progress import track
from selenium import webdriver
from selenium.webdriver.common.by import By
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
from .utils import find_click, save_cookies, recover_cookies

domain = "bookwalker.com.tw"


def validate_login(driver: webdriver.Chrome) -> bool:
    url = f"https://member.{domain}/login"
    driver.get(url)
    try:
        WebDriverWait(driver, 2).until(EC.url_changes(url))
        return True
    except TimeoutException:
        return False


def login(driver: webdriver.Chrome, username: str, password: str, error_on_captcha=False):
    """
    Leave username and password empty for manual login
    """
    if (recover_cookies(driver, f"https://{domain}/")
            and recover_cookies(driver, f"https://member.{domain}")
            and validate_login(driver)
            ):
        logging.info("Recovered cookies")
        return
    driver.delete_all_cookies()
    driver.get(f"https://{domain}")
    find_click(driver, By.CLASS_NAME, "topLoginStyle")
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "email")))

    if username or password:
        driver.find_element(By.ID, "email").send_keys(username)
        driver.find_element(By.ID, "password").send_keys(password)

        find_click(driver, By.ID, "login")
        with suppress(TimeoutException):
            WebDriverWait(driver, 2).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, "iframe[src^='https://www.recaptcha.net/recaptcha/api2/bframe']")))
            if error_on_captcha:
                raise RequiresCapcha()
    else:
        print("Manual login required")

    while True:
        cookies = driver.get_cookies()
        if any(c["name"] == "bwmember" for c in cookies):
            break

    save_cookies(driver, f"https://{domain}/")
    save_cookies(driver, f"https://member.{domain}")


def logout(driver: webdriver.Chrome):
    driver.get(f"https://member.{domain}")
    find_click(driver, By.CLASS_NAME, "headerLogoutBtn")


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


def download_book(driver: webdriver.Chrome, cfg: Config, book_uuid: str, overwrite):
    logging.info("Downloading book %s", book_uuid)
    driver.get(
        f"https://www.bookwalker.com.tw/browserViewer/{book_uuid}/trial_end")

    soup = bs4.BeautifulSoup(driver.page_source, "lxml")
    product_id = soup.find("meta", {"property": "og:url"})["content"].split("/")[-1]  # type: ignore[index]
    logging.debug("Product ID for book %s is %s", book_uuid, product_id)
    authors = []
    for data in soup.find_all(class_="writer_data"):
        for span in cast(bs4.Tag, data).find_all("span"):
            authors.append(span.text.strip())
    title = soup.head.title.text.strip()  # type: ignore[union-attr]
    if not title:
        raise ValueError("Title not found")

    save_dir = Path(f"babies/{title}")
    save_dir.mkdir(exist_ok=True, parents=True)
    meta_path = save_dir / "meta.json"
    meta_path.write_text(json.dumps(
        {"title": title, "authors": authors},
        ensure_ascii=False, indent=2), encoding = "utf-8")

    recover_cookies(driver, f"https://pcreader.{domain}")

    driver.get(f"https://www.bookwalker.com.tw/browserViewer/{product_id}/read")

    WebDriverWait(driver, 10).until(
        EC.url_contains(f"pcreader.{domain}"))

    driver.set_window_size(*cfg.viewer_size)  # size of bw page

    driver.switch_to.window(driver.window_handles[-1])

    with suppress(TimeoutException):
        WebDriverWait(driver, 10).until(EC.presence_of_element_located(
            (By.ID, "pageSliderCounter"))
        )

    if "Error 998" in driver.page_source:
        logging.error("Error 998: Must log out from another device")
        raise Error998()

    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, ".currentScreen canvas")))

    WebDriverWait(driver, 30).until(
        EC.invisibility_of_element_located((By.CLASS_NAME, "progressbar")))

    save_cookies(driver, driver.current_url)
    _, total_pages = get_pages(driver)
    prev_imgs = deque[bytes](maxlen=2)  # used for checking update for 2 buffers
    max_retries = 30

    logging.info("Titled %s by %s", title, ", ".join(authors))
    logging.info("Total pages: %s", total_pages)

    menu_name = get_menu_name(driver)
    go2page(driver, menu_name, 1)

    for current_page in track(range(1, total_pages + 1), description="Downloading", total=total_pages):
        retry = 0
        savename = save_dir / f"page_{current_page}.png"
        if savename.exists() and not overwrite:
            logging.debug("Page %s already exists, skipping", current_page)
            continue
        go2page(driver, menu_name, current_page)
        while current_page != get_pages(driver)[0]:
            sleep(0.1)
        wait4loading(driver)
        logging.debug("Getting page %s out of %s", current_page, total_pages)
        canvas = driver.find_element(By.CSS_SELECTOR, ".currentScreen canvas")
        while retry < max_retries:
            canvas_base64 = driver.execute_script(
                "return arguments[0].toDataURL('image/png').slice(21);", canvas)
            img_bytes = b64decode(canvas_base64)
            img = Image.open(io.BytesIO(img_bytes))
            if all(all(v == 0 for v in c) for c in img.getdata()):
                logging.debug("Blank page %s, treated as unloaded page", current_page)
            elif img_bytes not in prev_imgs:
                prev_imgs.append(img_bytes)
                break
            retry += 1
            logging.debug("Retrying page %s (%s/%s)", current_page, retry, max_retries)
            sleep(0.3)
        if retry == max_retries:
            logging.warning("Potentially repeated page %s", current_page)
        img.save(savename)
        logging.debug("Saved page %s", current_page)

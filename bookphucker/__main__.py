import argparse
import sys
import ujson as json
import bs4
import io
import logging
from rich.progress import track
from typing import Any
from selenium import webdriver
from selenium.webdriver.common.by import By
# from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from time import sleep
from urllib.parse import urlparse
from getpass import getpass
from pathlib import Path
from bookphucker import Config
from contextlib import suppress
from PIL import Image
from platformdirs import user_cache_dir
from base64 import b64decode
from collections import deque

config_path = Path("config.json")
cache_path = Path(user_cache_dir("bookphucker", ensure_exists=True))
cookies_path = cache_path / "cookies.json"


def recover_cookies(driver: webdriver.Chrome) -> bool:
    url = "https://member.bookwalker.jp/app/03/my/profile"
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


def login(driver: webdriver.Chrome, username: str, password: str):
    driver.delete_all_cookies()
    url = f"https://bookwalker.jp/"
    driver.get(url)
    driver.find_element(By.CLASS_NAME, "bw_btn-login").click()
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "mailAddress")))

    driver.find_element(By.ID, "mailAddress").send_keys(username)
    driver.find_element(By.ID, "password").send_keys(password)

    try:
        driver.find_element(By.ID, "loginBtn").click()
    except NoSuchElementException:
        driver.find_element(By.ID, "recaptchaLoginBtn").click()

    while True:
        cookies = driver.get_cookies()
        if any(c["name"] == "bwmember" for c in cookies):
            cookies_path.write_text(json.dumps(cookies))
            break


def wait4loading(driver: webdriver.Chrome, timeout: int = 30):
    WebDriverWait(driver, timeout).until_not(
        lambda x: any(e.is_displayed() for e in x.find_elements(By.CLASS_NAME, "loading")))


def get_pages(driver: webdriver.Chrome):
    while True:
        page_counter = driver.find_element(By.ID, "pageSliderCounter")
        with suppress(ValueError):
            current_page, total_pages = map(int, page_counter.text.split("/"))
            break
    return current_page, total_pages


def get_menu_name(driver: webdriver.Chrome) -> str:
    obj_name = driver.execute_script(
        "for (let k in NFBR.a6G.Initializer){if (NFBR.a6G.Initializer[k]['menu'] !== undefined){ return k; }}")
    return f"NFBR.a6G.Initializer.{obj_name}.menu"


def go2page(driver: webdriver.Chrome, menu_name: str, page: int):
    driver.execute_script(f"{menu_name}.options.a6l.moveToPage({page-1});")


def download_book(driver: webdriver.Chrome, cfg: Config, book_uuid: str, logger: logging.Logger):
    logger.info("Downloading book %s", book_uuid)
    driver.get(f"https://bookwalker.jp/{book_uuid}/")
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
        driver.find_element(By.CLASS_NAME, "gdpr-accept").click()

    read_button = driver.find_element(
        By.CLASS_NAME, "p-main__button").find_element(By.TAG_NAME, 'a')
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable(read_button))
    webdriver.ActionChains(driver).scroll_to_element(read_button).perform()
    read_button.click()

    save_dir = Path(f"babies/{title}")
    save_dir.mkdir(exist_ok=True, parents=True)
    meta_path = save_dir / "meta.json"
    meta_path.write_text(json.dumps(
        {"title": title, "authors": authors},
        ensure_ascii=False, indent=2))

    driver.switch_to.window(driver.window_handles[-1])

    wait4loading(driver)
    if "ERROR998" in driver.page_source:
        logger.error("Error 998: Must log out from another device")

    with suppress(TimeoutException):
        WebDriverWait(driver, 10).until(EC.presence_of_element_located(
            (By.ID, "pageSliderCounter"))
        )

    _, total_pages = get_pages(driver)
    prev_imgs = deque[bytes](maxlen=2)  # used for checking update for 2 buffers
    max_retries = 30
    logger.info("Total pages: %s", total_pages)

    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, ".currentScreen canvas")))
    menu_name = get_menu_name(driver)
    sleep(5)

    go2page(driver, menu_name, 1)
    sleep(2)

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
            if img_bytes not in prev_imgs:
                prev_imgs.append(img_bytes)
                break
            retry += 1
            logger.debug("Retrying page %s (%s/%s)", current_page, retry, max_retries)
            sleep(0.3)
        if retry == max_retries:
            logger.warning("Potential repeated page %s", current_page)
        img = Image.open(io.BytesIO(img_bytes))
        img.save(save_dir / f"page_{current_page}.png")
        logger.debug("Saved page %s", current_page)
        # canvas_pt.send_keys(Keys.ARROW_LEFT).perform()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("book_pages", help="The page url or book uuid", nargs='+')

    args = parser.parse_args()
    book_uuids = list[str]()

    for book_page in args.book_pages:
        if book_page.startswith("http"):
            book_url = urlparse(book_page)
            book_uuid = book_url.path
        else:
            book_uuid = book_page
        book_uuids.append(book_uuid.strip('/'))

    print(f"Book UUIDs:\n{'\n'.join(book_uuids)}\n")

    cfg = Config()

    if not config_path.exists():
        user_input = input(
            "Config file not found. Would you like to create one? (Y/n) ").strip().lower() or "y"
        if user_input == "y":
            username = input("Enter your username: ") or None
            password = getpass("Enter your password: ") or None
            cfg = Config(username=username, password=password)
            config_path.write_text(json.dumps(cfg.model_dump(mode="json"), indent=2))
            print(f"Config file created at {config_path}")
    else:
        print(f"Config file found at {config_path}")
        cfg = Config.model_validate_json(config_path.read_text())

    driver = cfg.get_webdriver()
    logger = cfg.get_logger()

    try:

        # if recover_cookies(driver):
        #     print(f"Recovered cookies from {cookies_path}")
        # else:
        #     print("Invalid cookies. Please login.")
        username = cfg.username or input("Enter your username: ")
        password = cfg.password or getpass("Enter your password: ")
        login(driver, username, password)

        for book_uuid in book_uuids:
            download_book(driver, cfg, book_uuid, logger)

    except Exception as e:
        Path("error.html").write_text(driver.page_source)
        Path("error.png").write_bytes(driver.get_screenshot_as_png())
        logger.error("An error occurred. Please check error.html and error.png for more information.")
        raise e
    except KeyboardInterrupt:
        print("Exiting...")
    finally:
        driver.get("https://member.bookwalker.jp/app/03/logout")
        driver.quit()


sys.exit(main())

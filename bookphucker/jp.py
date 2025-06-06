import ujson as json
import bs4
import io
import logging
import time
from rich.progress import track
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.common.exceptions import JavascriptException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from time import sleep
from pathlib import Path
from bookphucker import Config
from contextlib import suppress
from PIL import Image
from base64 import b64decode
from collections import deque
from .exc import RequiresCapcha
from .utils import find_click, save_cookies, recover_cookies

domain = "bookwalker.jp"


def validate_login(driver: webdriver.Chrome) -> bool:
    url = f"https://member.{domain}/app/03/my/profile"
    driver.get(url)
    with suppress(TimeoutException):
        WebDriverWait(driver, 1).until(lambda x: "ES0001" in x.page_source)
        return False
    try:
        WebDriverWait(driver, 2).until(EC.url_to_be(url))
        return True
    except TimeoutException:
        return False


def login(driver: webdriver.Chrome, username: str, password: str, error_on_captcha=False):
    """
    Leave username and password empty for manual login
    """
    if (recover_cookies(driver, f"https://{domain}/")
        and recover_cookies(driver, f"https://member.{domain}/app/03/my/profile")
            and validate_login(driver)):
        logging.info("Recovered cookies")
        return
    driver.delete_all_cookies()
    driver.get(f"https://{domain}/")
    driver.execute_script("sendGa(1,'グローバルナビ','クリック','ヘッダログイン');")
    driver.get(f"https://member.{domain}/app/03/webstore/cooperation?r=top%2F")
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "mailAddress")))

    if username or password:
        sleep(2)
        driver.find_element(By.ID, "mailAddress").send_keys(username)
        sleep(.2)
        driver.find_element(By.ID, "password").send_keys(password)
        sleep(.2)

        try:
            find_click(driver, By.ID, "loginBtn", 1)
        except NoSuchElementException:
            find_click(driver, By.ID, "recaptchaLoginBtn")
            # check if google recaptcha iframe exists
            with suppress(TimeoutException):
                WebDriverWait(driver, 2).until(
                    EC.visibility_of_element_located(
                        (By.CSS_SELECTOR,
                         "iframe[src^='https://www.recaptcha.net/recaptcha/api2/bframe']")))
                if error_on_captcha:
                    raise RequiresCapcha()
    else:
        print("Manual login required")

    init_time = time.time()
    timeout = 10
    with suppress(NoSuchElementException):
        if driver.find_element(
            By.CSS_SELECTOR,
            "iframe[src^='https://www.recaptcha.net/recaptcha/api2/bframe']"
            ).is_displayed():
            timeout = 180
    while True:
        cookies = driver.get_cookies()
        if any(c["name"] == "bwmember" for c in cookies):
            break
        if time.time() - init_time > timeout:
            raise TimeoutException("Cookies retrieval timeout")
        sleep(.1)

    save_cookies(driver, f"https://{domain}/")
    save_cookies(driver, f"https://member.{domain}/app/03/my/profile")


def logout(driver: webdriver.Chrome):
    driver.get(f"https://member.{domain}/app/03/my/profile")
    find_click(driver, By.CLASS_NAME, "l-header__logout")


def wait4loading(driver: webdriver.Chrome, timeout: int = 30):
    # wait until all loading overlays have disappeared
    WebDriverWait(driver, timeout).until_not(
        lambda d: any(e.is_displayed()
        for e in d.find_elements(By.CLASS_NAME, "loading"))
    )
    print(e.attibute("visibility") for e in driver.find_elements(By.CLASS_NAME, "loading"))

def get_menu(driver: webdriver.Chrome) -> str:
    obj_name = driver.execute_script(
        "for (let k in NFBR.a6G.Initializer){"
        "if (NFBR.a6G.Initializer[k]['menu'] !== undefined){ return k; }}")
    return f"NFBR.a6G.Initializer.{obj_name}.menu"

def get_total_pages(driver: webdriver.Chrome):
    return driver.execute_script(
        f"return {get_menu(driver)}.model.attributes.a2u.X2g.length")

def get_total_spreads(driver: webdriver.Chrome):
    return driver.execute_script(
        f"return {get_menu(driver)}.model.attributes.a2u.X2g.length")

def get_current_page(driver: webdriver.Chrome):
    pages = driver.execute_script(
        f"return {get_menu(driver)}.model.attributes.viewera6e.getPageIndex()")
    return pages+1

def get_current_spread(driver: webdriver.Chrome):
    return 1 + driver.execute_script(
        f"return {get_menu(driver)}.model.attributes.viewera6e.getSpreadIndex()")

def go2page(driver: webdriver.Chrome, page: int):
    driver.execute_script(f"{get_menu(driver)}.options.a6l.moveToPage({page-1});")

def go2spread(driver: webdriver.Chrome, spread: int):
    page_index = driver.execute_script(
        f"return {get_menu(driver)}.model.attributes.a2u.X2g[{spread-1}].pageIndex")
    go2page(driver, page_index+1)

def download_book(driver: webdriver.Chrome, cfg: Config, book_uuid: str, overwrite):
    logging.info("Downloading book %s", book_uuid)
    driver.get(f"https://{domain}/de{book_uuid}/")
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CLASS_NAME, "t-c-product-main-data__title")))

    soup = bs4.BeautifulSoup(driver.page_source, "lxml")

    title = soup.find(class_="t-c-product-main-data__title").text.strip()
    authors_ml = soup.find(class_="t-c-product-main-data__authors").find_all("dd")
    authors = [a.text.strip() for a in authors_ml]
    if not title:
        raise ValueError("Title not found")

    logging.info("Titled %s by %s", title, ", ".join(authors))

    driver.set_window_size(*cfg.viewer_size)

    with suppress(TimeoutException):
        WebDriverWait(driver, 3).until(EC.presence_of_element_located(
            (By.CLASS_NAME, "gdpr-accept"))
        )
        find_click(driver, By.CLASS_NAME, "gdpr-accept")

    driver.get(
        f"https://member.{domain}/app/03/webstore/cooperation"
        f"?r=BROWSER_VIEWER/{book_uuid}/https%3A%2F%2Fbookwalker.jp%2Fde{book_uuid}%2F")

    save_dir = Path(f"babies/{title}")
    save_dir.mkdir(exist_ok=True, parents=True)
    meta_path = save_dir / "meta.json"
    meta_path.write_text(json.dumps(
        {"title": title, "authors": authors},
        ensure_ascii=False, indent=2), encoding = "utf-8")

    driver.switch_to.window(driver.window_handles[-1])

    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, ".currentScreen canvas")))

    WebDriverWait(driver, 30).until(
        EC.invisibility_of_element_located((By.CLASS_NAME, "progressbar")))

    init_time = time.time()
    while True:
        try:
            total_spreads = get_total_spreads(driver)
            break
        except JavascriptException:
            if time.time() - init_time > 10:
                raise TimeoutException("Total spreads retrieval timeout")
    prev_imgs = deque[bytes](maxlen=2)  # used for checking update for 2 buffers
    max_retries = 30
    logging.info("Total spreads: %s", total_spreads)

    go2spread(driver, 1)
    sleep(2)

    for current_spread in track(range(1, total_spreads + 1), description="Downloading", total=total_spreads):
        retry = 0
        savename = save_dir / f"page_{current_spread}.png"
        if savename.exists() and not overwrite:
            logging.debug("page %s already exists, skipping", current_spread)
            continue
        go2spread(driver, current_spread)
        while get_current_spread(driver) != current_spread:
            sleep(0.1)
        sleep(.1)
        wait4loading(driver)
        logging.debug("Getting page %s out of %s", current_spread, total_spreads)
        canvas = driver.find_element(By.CSS_SELECTOR, ".currentScreen canvas")
        while retry < max_retries:
            canvas_base64 = driver.execute_script(
                "return arguments[0].toDataURL('image/png').slice(21);", canvas)
            img_bytes = b64decode(canvas_base64)
            img = Image.open(io.BytesIO(img_bytes))
            if all(all(v == 0 for v in c) for c in img.getdata()):
                logging.debug("Blank page %s, treated as unloaded page", current_spread)
            elif img_bytes not in prev_imgs:
                prev_imgs.append(img_bytes)
                break
            retry += 1
            logging.debug("Retrying page %s (%s/%s)", current_spread, retry, max_retries)
            sleep(0.3)
        if retry == max_retries:
            logging.warning("Potentially repeated page %s", current_spread)
        img.save(savename)
        logging.debug("Saved page %s", current_spread)

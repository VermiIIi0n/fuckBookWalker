import argparse
import sys
import ujson as json
import logging
import requests
from shutil import move, rmtree
from urllib.parse import urlparse
from getpass import getpass
from pathlib import Path
from contextlib import suppress
from selenium.common.exceptions import WebDriverException
from bookphucker import Config
from bookphucker.exc import RequiresCapcha, Error998
from bookphucker.commonvars import config_path, cache_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("book_pages", help="The page url or book uuid", nargs='+')
    parser.add_argument("-r", "--region", help="The region of the bookwalker site",
                        default="auto", choices=["jp", "tw", "auto"])
    parser.add_argument("--no-cache", help="Clear cache directory (cookies, etc.)",
                        action="store_true")
    parser.add_argument("--overwrite", help="Overwrite existing files",
                        action="store_true")

    args = parser.parse_args()
    book_uuids = list[str]()
    region = args.region

    print(f"Book UUIDs:\n\n")

    for book_page in args.book_pages:
        if "bookwalker" in book_page:
            if not book_page.startswith("http"):
                book_page = "https://" + book_page
            book_url = urlparse(book_page)
            if ".jp" in book_url.hostname:
                if region == "auto":
                    region = "jp"
                book_uuid = book_url.path
                print(f"{book_uuid}")
            elif ".com.tw" in book_url.hostname:
                if region == "auto":
                    region = "tw"
                book_id = ''
                if book_url.path.startswith("/product/"):
                    book_id = book_url.path.removeprefix("/product/").split("/")[0]
                    r = requests.head(
                        f"https://www.bookwalker.com.tw/browserViewer/{book_id}/trial")
                    book_url = urlparse(r.headers["Location"])
                query = book_url.query
                book_uuid = dict([param.split("=")
                                 for param in query.split("&")])["cid"]
                print(f"{book_uuid}{f" ({book_id})" if book_id else ''}")
        else:
            book_uuid = book_page
        book_uuids.append(book_uuid.strip('/')[-36:])

    match region:
        case "jp" | "auto":
            from bookphucker.jp import login, download_book, logout
        case "tw":
            from bookphucker.tw import login, download_book, logout

    cfg = Config()

    if not config_path.exists():
        user_input = input(
            "Config file not found. Would you like to create one? (Y/n) ").strip().lower() or "y"
        if user_input == "y":
            username = input("Enter your username: ") or None
            password = getpass("Enter your password: ") or None
            cfg = Config(username=username, password=password)
            config_path.write_text(
                json.dumps(cfg.model_dump(mode="json"), indent=2), encoding = "utf-8")
            print(f"Config file created at {config_path}")
    else:
        print(f"Config file found at {config_path}")
        d = json.loads(config_path.read_text())
        cfg, updated = Config.from_dict(d)
        if updated:
            move(config_path, config_path.with_suffix(".bak"))
            config_path.write_text(
                json.dumps(cfg.model_dump(mode="json"), indent=2), encoding = "utf-8")
            print(f"Config file updated at {config_path}")

    if args.no_cache and cache_path.exists():
        rmtree(cache_path)
        cache_path.mkdir()
        print(f"Cache directory cleared at {cache_path}")

    driver = cfg.get_webdriver()
    cfg.config_logging()

    try:
        username = '' if cfg.manual_login else (
            cfg.username or input("Enter your username: "))
        password = '' if cfg.manual_login else (
            cfg.password or getpass("Enter your password: "))
        max_login_retries = 1
        login_retry = 0
        manual_login = cfg.manual_login or not any([username, password])
        if manual_login and cfg.headless:
            print("Manual login required, but browser is headless.")
            user_input = input(
                "Would you like to stay headless? (Y/n) ").strip().lower() or "y"
            if user_input != "y":
                driver.quit()
                cfg.headless = False
                driver = cfg.get_webdriver()
        while True:
            try:
                login(driver, username, password, error_on_captcha=cfg.headless)
            except RequiresCapcha:
                print("Captcha required, but browser is headless.")
                user_input = input(
                    "Would you like to continue with non-headless browser? (y/N) ").strip().lower() or "y"
                if user_input != "y":
                    return 2
                driver.quit()
                cfg.headless = False
                driver = cfg.get_webdriver()
                login(driver, username, password)

            try:
                for book_uuid in book_uuids:
                    download_book(driver, cfg, book_uuid, overwrite=args.overwrite)
            except Error998:
                login_retry += 1
                if login_retry > max_login_retries:
                    raise
                logging.warning("Retrying login %s/%s", login_retry, max_login_retries)
                logout(driver)
                continue
            break
    except Exception as e:
        Path("error.html").write_text(driver.page_source, encoding = "utf-8")
        Path("error.png").write_bytes(driver.get_screenshot_as_png())
        logging.error(
            "An error occurred. Please check error.html and error.png for more information.")
        raise e
    except KeyboardInterrupt:
        print("Exiting...")
    finally:
        with suppress(WebDriverException):
            driver.quit()


sys.exit(main())

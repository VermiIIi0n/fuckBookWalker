import argparse
import sys
import ujson as json
import logging
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
                        default="jp", choices=["jp", "tw"])
    parser.add_argument("--no-cache", help="Clear cache directory (cookies, etc.)",
                        action="store_true")

    args = parser.parse_args()
    match args.region:
        case "jp":
            from bookphucker.jp import login, download_book, logout
        case "tw":
            raise NotImplementedError("TW region is not supported yet.")
            # from bookphucker.tw import login, download_book, logout
    book_uuids = list[str]()

    for book_page in args.book_pages:
        if book_page.startswith("http"):
            book_url = urlparse(book_page)
            book_uuid = book_url.path
        else:
            book_uuid = book_page
        book_uuids.append(book_uuid.strip('/')[-36:])

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
        d = json.loads(config_path.read_text())
        cfg, updated = Config.from_dict(d)
        if updated:
            move(config_path, config_path.with_suffix(".bak"))
            config_path.write_text(json.dumps(cfg.model_dump(mode="json"), indent=2))
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
                "Would you like to continue with non-headless browser? (Y/n) ").strip().lower() or "y"
            if user_input != "y":
                return 1
            driver.quit()
            cfg.headless = False
            driver = cfg.get_webdriver()
        while True:
            try:
                login(driver, username, password, error_on_captcha=cfg.headless)
            except RequiresCapcha:
                print("Captcha required, but browser is headless.")
                user_input = input(
                    "Would you like to continue with non-headless browser? (Y/n) ").strip().lower() or "y"
                if user_input != "y":
                    return 2
                driver.quit()
                cfg.headless = False
                driver = cfg.get_webdriver()
                login(driver, username, password)

            try:
                for book_uuid in book_uuids:
                    download_book(driver, cfg, book_uuid)
            except Error998:
                login_retry += 1
                if login_retry > max_login_retries:
                    raise
                logging.warning("Retrying login %s/%s", login_retry, max_login_retries)
                logout(driver)
                continue
            break
    except Exception as e:
        Path("error.html").write_text(driver.page_source)
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

import argparse
import sys
import ujson as json
from urllib.parse import urlparse
from getpass import getpass
from pathlib import Path
from contextlib import suppress
from selenium.common.exceptions import WebDriverException
from bookphucker import Config
from bookphucker.exc import RequiresCapcha, Error998
from bookphucker.commonvars import cookies_path, config_path, cache_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("book_pages", help="The page url or book uuid", nargs='+')
    parser.add_argument("-r", "--region", help="The region of the bookwalker site",
                        default="jp", choices=["jp", "tw"])

    args = parser.parse_args()
    match args.region:
        case "jp":
            from bookphucker.jp import recover_cookies, login, download_book, logout
        case "tw":
            raise NotImplementedError("TW region is not supported yet.")
            # from bookphucker.tw import recover_cookies, login, download_book, logout
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
        max_login_retries = 1
        login_retry = 0
        while True:
            try:
                login(driver, username, password, error_on_captcha=cfg.headless)
            except RequiresCapcha:
                print("Captcha required, but browser is headless.")
                user_input = input(
                    "Would you like to continue with non-headless browser? (Y/n) ").strip().lower() or "y"
                if user_input != "y":
                    return 1
                driver.quit()
                cfg.headless = False
                driver = cfg.get_webdriver()
                login(driver, username, password)

            try:
                for book_uuid in book_uuids:
                    download_book(driver, cfg, book_uuid, logger)
            except Error998:
                login_retry += 1
                if login_retry > max_login_retries:
                    raise
                logger.warning("Retrying login %s/%s", login_retry, max_login_retries)
                logout(driver)
                continue
            break
    except Exception as e:
        Path("error.html").write_text(driver.page_source)
        Path("error.png").write_bytes(driver.get_screenshot_as_png())
        logger.error(
            "An error occurred. Please check error.html and error.png for more information.")
        raise e
    except KeyboardInterrupt:
        print("Exiting...")
    finally:
        with suppress(WebDriverException):
            logout(driver)
            driver.quit()


sys.exit(main())

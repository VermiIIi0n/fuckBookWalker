# Unpolished bookwalker.jp scraper

> It just works. -- Todd Howard

## TODO List

- [ ] Image `EPUB` export
- [ ] `OCR` integration
  - [ ] OCR text `EPUB` export
  - [ ] OCR to database

## Usage

### Installation

Requires Chrome/Chromium to be installed. For Chromium, you need to modify `"browser"` in `config.json` to `"chromium"`.

```bash
pip install -U poetry
cd fuckBookWalker
poetry install
```

### Running

```bash
poetry run python bookphucker <url or uuid of books>
```

You should see something like this.
![sample](./imgs/sample.png)

## Common Issues

### Error 998 Stuck after showing title & authors

Bookwalker doesn't allow multiple reading sessions, sometimes improperly quitting the page can cause this issue.

Login using a browser and then logout can resolve it.

### Cannot log in

You may encounter CAPTCHA during login.

Modify `"headless"` to `false` in `config.json` and then manually finish CAPTCHA.

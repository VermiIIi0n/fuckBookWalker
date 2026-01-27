# Unpolished bookwalker scraper

> It just works. -- Todd Howard

## TODO List

- [ ] Image `EPUB` export
- [ ] `OCR` integration
  - [ ] OCR text `EPUB` export
  - [ ] OCR to database

## Usage

### Installation

Requires Chrome/Chromium to be installed. For Chromium, you need to modify `"browser"` in `config.json` to `"chromium"`.
By using webdriver it is also required that you do not use snap or flatpack as webdriver cannot find the chrome binary. 
```bash
pip install -U poetry
cd fuckBookWalker
poetry install
```

### Running

```bash
poetry run python bookphucker <url or UUID of books>
```

You should see something like this.
![sample](./imgs/sample.png)

Another example, here of batch operation on UUIDs
```bash
poetry run python bookphucker  a70143ab-0be7-49d8-8efc-7b7ee104a0b4 e99937dd-7c18-4cf2-8547-0230864775b4
```

### Configuration

wip...

By default, `bookphucker` will try to reuse previous `cookies`, using `--no-cache` to clear `cookies`.

## Common Issues
runing via --no-cache

and set headless to false in config.json

### Cannot log in

You may encounter CAPTCHA during the login process.

`bookphucker` will ask you to use non-headless mode to pass the captcha if your config sets `headless` to `true`.

### cannot connect to chrome at 127.0.0.1:38865
kill all chrome instanses/processes as the program does not properly kill forked instances when done, which might cause gridlocks.
On linux you can do
``` bash
pkill chrome
```
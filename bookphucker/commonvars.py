from pathlib import Path
from platformdirs import user_cache_dir

config_path = Path("config.json")
cache_path = Path(user_cache_dir("bookphucker", ensure_exists=True))
cookies_path = cache_path / "cookies.json"

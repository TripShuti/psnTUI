import json
from pathlib import Path
from platformdirs import user_config_dir


APP_DIR = Path(user_config_dir("psntui", ensure_exists=True))
CONFIG_PATH = APP_DIR / "config.json"
DB_PATH = APP_DIR / "trophies.db"


def get_config_path() -> Path:
    return CONFIG_PATH


def get_db_path() -> Path:
    return DB_PATH


def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {}


def save_config(config: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2))


def is_authenticated() -> bool:
    config = load_config()
    return bool(config.get("npsso"))


def validate_npsso(npsso: str) -> str | None:
    from psnawp_api import PSNAWP
    try:
        psnawp = PSNAWP(npsso_cookie=npsso)
        client = psnawp.me()
        online_id = client.online_id
        return online_id
    except Exception:
        return None

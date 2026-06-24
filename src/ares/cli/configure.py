import tyro
import enum
import yaml
from pathlib import Path
from typing import Any
from typing_extensions import Annotated


CLI_CACHE_DIR = Path.home() / ".ares"
CONFIG_FILE = CLI_CACHE_DIR / "config.yaml"


class Configuration(enum.Enum):
    SAVE_LOCATION = "save-loc"


def configure(key: tyro.conf.EnumChoicesFromValues[Configuration], value: str | None = None, /):
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r") as f:
            configs = yaml.safe_load(f)
    else:
        configs = {}

    if value is None:
        if key.name not in configs:
            print("Not set")
        else:
            print(configs[key.name])
        exit(0)

    configs[key.name] = value

    if not CLI_CACHE_DIR.exists():
        CLI_CACHE_DIR.mkdir()

    with open(CONFIG_FILE, "w") as f:
        yaml.safe_dump(configs, f)


def get_setting(key: Configuration) -> Any:
    if not CONFIG_FILE.exists():
        raise RuntimeError("Not configured")

    with open(CONFIG_FILE, "r") as f:
        configs = yaml.safe_load(f)

    if key.name not in configs:
        raise RuntimeError("Not configured")

    return configs[key.name]

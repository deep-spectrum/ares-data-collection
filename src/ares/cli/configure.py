import typer
from enum import Enum
import yaml
from pathlib import Path
from typing import Any


app = typer.Typer()


CLI_CACHE_DIR = Path.home() / ".ares"
CONFIG_FILE = CLI_CACHE_DIR / "config.yaml"


class Configuration(str, Enum):
    save_location = "save-path"


@app.command()
def configure(key: Configuration, value: str):
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r") as f:
            configs = yaml.safe_load(f)
    else:
        configs = {}

    configs[key.value] = value

    if not CLI_CACHE_DIR.exists():
        CLI_CACHE_DIR.mkdir()

    with open(CONFIG_FILE, "w") as f:
        yaml.safe_dump(configs, f)


def get_setting(key: Configuration) -> Any:
    if not CONFIG_FILE.exists():
        raise RuntimeError("Not configured")

    with open(CONFIG_FILE, "r") as f:
        configs = yaml.safe_load(f)

    if key.value not in configs:
        raise RuntimeError("Not configured")

    return configs[key.value]

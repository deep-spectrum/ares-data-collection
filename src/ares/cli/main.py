from .collect import collect
from .configure import configure
from .start import start
from .spot_check import spot_check
import tyro


def main():
    tyro.extras.subcommand_cli_from_dict(
        {
            "collect": collect,
            "configure": configure,
            "start": start,
            "spot-check": spot_check,
        }
    )


if __name__ == '__main__':
    main()

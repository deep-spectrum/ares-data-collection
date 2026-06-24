from .collect import collect
from .configure import configure
from .start import start
import tyro


def main():
    tyro.extras.subcommand_cli_from_dict(
        {
            "collect": collect,
            "configure": configure,
            "start": start,
        }
    )


if __name__ == '__main__':
    main()

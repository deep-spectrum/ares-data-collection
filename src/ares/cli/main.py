from .collect import collect
from .configure import configure
import tyro


def main():
    tyro.extras.subcommand_cli_from_dict(
        {
            "collect": collect,
            "configure": configure,
        }
    )


if __name__ == '__main__':
    main()

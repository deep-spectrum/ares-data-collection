from .collect import app as collect_app
from .configure import app as configure_app
import typer


app = typer.Typer()
app.add_typer(collect_app)
app.add_typer(configure_app)


def main():
    app()


if __name__ == '__main__':
    main()

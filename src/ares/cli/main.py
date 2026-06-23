from .collect import app as collect_app
import typer


app = typer.Typer()
app.add_typer(collect_app)


# TODO: Some config commands


def main():
    app()


if __name__ == '__main__':
    main()

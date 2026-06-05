from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.widgets import Placeholder


class Header(Placeholder):
    pass


class Footer(Placeholder):
    pass


class AresScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header(id='Header')
        yield Footer(id='Footer')


class LayoutApp(App):
    def on_ready(self) -> None:
        self.push_screen(AresScreen())


def main():
    app = LayoutApp()
    app.run()


if __name__ == "__main__":
    main()

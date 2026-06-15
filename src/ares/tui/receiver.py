from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, Static
from textual.containers import Container


class GridLayout(Container):

    def compose(self) -> ComposeResult:
        with Container(id='dashes'):
            sm_status = Static('SM Status & API Info', classes='box')
            sm_status.border_title = 'SM Information'
            yield sm_status

            sm_logs = Static('SM Logs', classes='box')
            sm_logs.border_title = 'SM Logs'
            yield sm_logs

            sm_control = Static('SM Control Panel', classes='box')
            sm_control.border_title = 'SM Control'
            yield sm_control

            lora_logs = Static('LoRa Logs', classes='box')
            lora_logs.border_title = 'LoRa Logs'
            yield lora_logs


class AresReceiverScreen(Screen):
    CSS_PATH = "receiver.tcss"
    def compose(self) -> ComposeResult:
        yield Header(id='Header')
        yield GridLayout(id='grid')
        yield Footer(id='Footer')


class AresReceiverLayoutApp(App):
    TITLE = "Ares Receiver"

    def on_ready(self) -> None:
        self.push_screen(AresReceiverScreen())


def main():
    app = AresReceiverLayoutApp()
    app.run()


if __name__ == "__main__":
    main()

from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, Static
from textual.containers import Container


class GridLayout(Container):
    def compose(self) -> ComposeResult:
        with Container(id='dashes'):
            status_board = Static('Transmitter Status Board', classes='box')
            status_board.border_title = 'Status'
            yield  status_board

            log_board = Static('Transmitter Logs', classes='box')
            log_board.border_title = 'Logs'
            yield log_board

            node_status = Static('Node Status Board', classes='box')
            node_status.border_title = 'Node Statuses'
            yield node_status

            lora_log = Static('LoRa Logs', classes='box')
            lora_log.border_title = 'LoRa Logs'
            yield lora_log

            control_board = Static('Control Board', classes='box', id='control')
            control_board.border_title = 'Control'
            yield control_board

class AresTransmitterScreen(Screen):
    CSS_PATH = 'transmitter.tcss'

    def compose(self) -> ComposeResult:
        yield Header(id='Header')
        yield GridLayout(id='grid')
        yield Footer(id='Footer')


class AresTransmitterLayoutApp(App):
    TITLE = "Ares Transmitter"

    def on_ready(self) -> None:
        self.push_screen(AresTransmitterScreen())


def main():
    app = AresTransmitterLayoutApp()
    app.run()


if __name__ == "__main__":
    main()


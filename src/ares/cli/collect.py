import typer
from typing_extensions import Annotated
from ares.receiver import AresReceiver
from datetime import timedelta


app = typer.Typer()


@app.command('collect')
def collect(
        lora_port: Annotated[str, typer.Argument(help="The port the LoRa modem is connected to")],
        center: Annotated[float, typer.Argument(help="Center frequency in Hz")],
        bandwidth: Annotated[float, typer.Argument(help="Bandwidth in Hz")],
        duration: Annotated[float, typer.Argument(help="The duration of the capture in seconds")],
        gps_timestamping: Annotated[bool, typer.Option("--gps-ts", "-g", help="Use GPS timestamping")] = False,
        quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Run in quiet mode")] = False
):
    """
    Start data collection on an Ares receiver node.

    This will wait for the start signal from the transmitter.
    """

    rx = AresReceiver(lora_port, gps_timestamping)
    rx.start()

    some_path = ""

    try:
        rx.capture_data(center, bandwidth, timedelta(seconds=duration), some_path, quiet)
    except KeyboardInterrupt:
        rx.stop()
        print("No data captured")

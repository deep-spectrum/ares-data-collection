import typer
from typing_extensions import Annotated
from ares.receiver import AresReceiver
from datetime import timedelta, datetime
from .configure import get_setting, Configuration
from pathlib import Path


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
    rx_id = rx.node_id

    save_path = Path(get_setting(Configuration.save_location))
    if not save_path.exists():
        print(f"{save_path} does not exist.")
        raise typer.Exit(1)

    now = datetime.now()
    date_string = now.strftime("%Y-%m-%d-%H-%M-%S")
    save_path = save_path / date_string
    save_path.mkdir()

    save_path = save_path / f"rx{rx_id}"
    save_path.mkdir()

    try:
        rx.capture_data(center, bandwidth, timedelta(seconds=duration), save_path, quiet)
    except KeyboardInterrupt:
        rx.stop()
        print("No data captured")

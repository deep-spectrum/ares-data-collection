import tyro
from typing_extensions import Annotated
from ares.receiver import AresReceiver
from datetime import timedelta, datetime
from .configure import get_setting, Configuration
from pathlib import Path
from ares_iq_ext import datetime_from_timeval


def _start_notification(second: int, microsecond: int):
    dt: datetime = datetime_from_timeval(second, microsecond)
    print(f"Starting measurement at {dt.strftime('%I:%M:%S %p')}")


def collect(
        lora_port: Path,
        center: float,
        bandwidth: float,
        duration: float,
        /,
        gps_ts: Annotated[bool, tyro.conf.FlagCreatePairsOff, tyro.conf.arg(aliases=["-g"])] = False,
        quiet: Annotated[bool, tyro.conf.FlagCreatePairsOff, tyro.conf.arg(aliases=["-q"])] = False,
        now: Annotated[bool, tyro.conf.FlagCreatePairsOff] = False
):
    """
    Start data collection on an Ares receiver node. This will wait for the start signal from the transmitter.

    Args:
        lora_port: The port the LoRa modem is connected to.
        center: Center frequency in Hz.
        bandwidth: Bandwidth in Hz.
        duration: The duration of the capture in seconds.
        gps_ts: Use GPS timestamping.
        quiet: Run in quiet mode.
        now: Start measurement now.
    """

    rx = AresReceiver(str(lora_port), gps_ts, start_notif_cb=_start_notification)
    rx.start()
    rx_id = rx.node_id

    save_path = Path(get_setting(Configuration.SAVE_LOCATION))
    if not save_path.exists():
        print(f"{save_path} does not exist.")
        exit(1)

    now_ = datetime.now()
    date_string = now_.strftime("%Y-%m-%d-%H-%M-%S")
    save_path = save_path / date_string
    save_path.mkdir()

    save_path = save_path / f"rx{rx_id}"
    save_path.mkdir()

    try:
        print(f"Saving to {save_path}")
        print("Waiting for start signal")
        rx.capture_data(center, bandwidth, timedelta(seconds=duration), save_path, quiet, now=now)
    except KeyboardInterrupt:
        rx.stop()
        print("No data captured")

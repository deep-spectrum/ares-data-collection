import tyro
from typing_extensions import Annotated
from ares.receiver import AresReceiver, AresReceiverPolling
from datetime import timedelta, datetime
from .configure import get_setting, Configuration
from pathlib import Path
from ares_iq_ext import datetime_from_timeval
import shutil


def _start_notification(second: int, microsecond: int):
    dt: datetime = datetime_from_timeval(second, microsecond)
    print(f"Starting measurement at {dt.strftime('%I:%M:%S %p')}")


def _poll_results(nodes: dict[int, bool]):
    for node, ready in nodes.items():
        print(f"Ares {node - 1}: {'ready' if ready else 'not ready'}")


def collect(
        lora_port: Path,
        center: float,
        bandwidth: float,
        duration: float,
        /,
        gps_ts: Annotated[bool, tyro.conf.FlagCreatePairsOff, tyro.conf.arg(aliases=["-g"])] = False,
        quiet: Annotated[bool, tyro.conf.FlagCreatePairsOff, tyro.conf.arg(aliases=["-q"])] = False,
        now: Annotated[bool, tyro.conf.FlagCreatePairsOff] = False,
        poll_ids: Annotated[tuple[int, ...], tyro.conf.arg(aliases=["-p"])] = ()
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
        poll_ids: The node IDs to poll for. This will also designate the node as the polling node.
    """

    if not poll_ids:
        rx = AresReceiver(str(lora_port), gps_ts, start_notif_cb=_start_notification)
    else:
        poll_ids_set = set(poll_ids)
        rx = AresReceiverPolling(str(lora_port), gps_ts, 30.0, poll_ids_set, poll_cb=_poll_results)
        rx.start()
    rx_id = rx.node_id

    save_path = Path(get_setting(Configuration.SAVE_LOCATION))
    if not save_path.exists():
        print(f"{save_path} does not exist.")
        exit(1)

    now_ = datetime.now()
    date_string = now_.strftime("%Y-%m-%d-%H-%M-%S")
    unique_save_path = save_path / f"{center / 1e6}MHz-{date_string}"
    unique_save_path.mkdir()

    save_path = unique_save_path / f"rx{rx_id}"
    save_path.mkdir()

    try:
        print(f"Saving to {save_path}")
        print("Waiting for start signal")
        rx.stream_data(center, bandwidth, timedelta(seconds=duration), save_path, quiet, now=now)
    except KeyboardInterrupt:
        print("No data captured")
        shutil.rmtree(unique_save_path)
        if isinstance(rx, AresReceiverPolling):
            rx.stop()

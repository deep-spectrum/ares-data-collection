from ares.transmitter import AresTransmitter
import tyro
from pathlib import Path
from typing_extensions import Annotated
from datetime import datetime, timedelta
from ares_iq_ext import  datetime_from_timeval


def _start_notification(second: int, microsecond: int):
    dt: datetime = datetime_from_timeval(second, microsecond)
    print(f"Starting measurement at {dt.strftime('%I:%M:%S %p')}")


def start(lora_port: Path,
          delay_sec: int = 30,
          delay_usec: int = 0,
          /,
          gps_ts: Annotated[bool, tyro.conf.FlagCreatePairsOff, tyro.conf.arg(aliases=["-g"])] = False):
    """
    Tell the receiver nodes to start recording data.

    Args:
        lora_port: The port the LoRa modem is connected to.
        delay_sec: The amount of seconds to delay the start by.
        delay_usec: The amount of microseconds to delay the start by. Ignored if using GPS timestamping.
        gps_ts: Use GPS timestamping.
    """

    tx = AresTransmitter(str(lora_port), gps_ts, timedelta(minutes=3), start_notif_cb=_start_notification)
    tx.start(delay_sec, delay_usec)

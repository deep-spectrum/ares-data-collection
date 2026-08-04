import tyro
from typing_extensions import Annotated
from ares.receiver import AresReceiver, AresReceiverPolling
from datetime import timedelta, datetime
from .configure import get_setting, Configuration
from pathlib import Path
from ares_iq_ext import datetime_from_timeval
import shutil
from .termui import confirm
from ares_lora import LoraSerial, LoraSerialConfig
from threading import Event


def _start_notification(second: int, microsecond: int):
    dt: datetime = datetime_from_timeval(second, microsecond)
    print(f"Starting measurement at {dt.strftime('%I:%M:%S %p')}")


num_poll_calls = 1


def _poll_results(nodes: dict[int, bool]):
    global num_poll_calls
    print(f"--- Poll {num_poll_calls} ---")
    num_poll_calls += 1
    for node, ready in nodes.items():
        print(f"Ares {node}: {'ready' if ready else 'not ready'}")


def _get_save_path(dt: datetime) -> Path:
    save_path = Path(get_setting(Configuration.SAVE_LOCATION))
    if not save_path.exists():
        print(f"{save_path} does not exist")
        exit(1)
    date_string = dt.strftime("%Y-%m-%d-%H-%M-%S")
    return save_path / date_string


def _collect_now_cmd(lora_port: Path,
                    center: float | None,
                    bandwidth: float | None,
                    duration: float | None,
                    ref_level: float | None,
                    gps_ts: bool = False,
                    quiet: bool = False):
    if center is None:
        print("Center frequency must be specified if collecting data now")
        exit(1)
    if bandwidth is None:
        print("Bandwidth must be specified if collecting data now")
        exit(1)
    if duration is None:
        print("Duration must be specified if collecting data now")
        exit(1)
    if ref_level is None:
        print("Reference level must be specified if collecting data now")
        exit(1)

    unique_save_path = _get_save_path(datetime.now())

    lora_dev = LoraSerial(LoraSerialConfig(port=str(lora_port)))
    rx = AresReceiver(lora_dev, gps_ts)

    unique_save_path.mkdir()
    save_path = unique_save_path / f"rx{rx.node_id}"
    save_path.mkdir()

    try:
        print(f"Saving data to {save_path}")
        rx.stream_data(center, bandwidth, timedelta(seconds=duration), save_path, ref_level, quiet, now=True)
    except KeyboardInterrupt:
        print("No data collected")
        shutil.rmtree(unique_save_path)


def _collect_non_polling(lora_port: Path,
                        gps_ts: bool = False,
                        quiet: bool = False):
    run_ready = Event()

    # This is just here for the error message
    _ = _get_save_path(datetime.now())
    lora_dev = LoraSerial(LoraSerialConfig(str(lora_port)))
    rx_dev = AresReceiver(lora_dev, gps_ts, start_notif_cb=_start_notification)

    def _run_ready_event_handle(source_id: int, broadcasted: bool):
        print(f"Received notification that run was ready ({source_id}, {broadcasted})")
        run_ready.set()

    while True:
        lora_dev.register_run_ready_hook(_run_ready_event_handle)

        print("Waiting for coordinator node to become ready")
        run_ready.wait()
        lora_dev.register_run_ready_hook(None)
        run_ready.clear()

        configs = lora_dev.node_configs
        folder_dt = configs['folder_dt']
        assert isinstance(folder_dt, datetime)
        unique_save_path = _get_save_path(folder_dt)
        unique_save_path.mkdir()
        save_dir = unique_save_path / f"rx{rx_dev.node_id}"
        save_dir.mkdir()

        center = configs["center_freq"]
        bw = configs["bandwidth"]
        duration = configs["duration"]
        ref_level = configs["ref_level"]

        assert isinstance(center, (float, int))
        assert isinstance(bw, (float, int))
        assert isinstance(duration, int)
        assert isinstance(ref_level, (float, int))

        print("Waiting for start signal")
        rx_dev.stream_data(center, bw, timedelta(seconds=duration), save_dir, ref_level, quiet)


def _collect_polling(lora_port: Path,
                     center: float | None,
                     bandwidth: float | None,
                     duration: float | None,
                     ref_level: float | None,
                     gps_ts: bool = False,
                     quiet: bool = False):
    pass


def collect(
        lora_port: Path,
        /,
        center: float | None = None,
        bandwidth: float | None = None,
        duration: float | None = None,
        ref_level: float | None = None,
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

    try:
        if not poll_ids:
            rx = AresReceiver(str(lora_port), gps_ts, start_notif_cb=_start_notification)
            wait_msg = "Waiting for start signal"
        else:
            poll_ids_set = set(poll_ids)
            rx = AresReceiverPolling(str(lora_port), gps_ts, 30.0, poll_ids_set, poll_cb=_poll_results)
            rx.start()
            wait_msg = "Waiting until every node is ready"
    except OSError:
        print("Please turn on SM device or correct the network profile")
        return
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
        print(wait_msg)
        rx.stream_data(center, bandwidth, timedelta(seconds=duration), save_path, quiet, now=now,
                       continue_callback=confirm)
    except KeyboardInterrupt:
        print("No data captured")
        shutil.rmtree(unique_save_path)

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
    lora_dev.start_driver()
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
        print("Run complete. Rebooting node")
        lora_dev.reboot(5)
        lora_dev.start_driver()


def _check_configs(dt: datetime, center: float, bw: float, duration: int, ref_level: float, node: int,
                   lora_dev: LoraSerial) -> bool:
    configs = lora_dev.poll_node_config(node, 20.0, 5.0, "folder_dt", "bandwidth", "center_freq", "duration",
                                        "ref_level")
    return dt == configs["folder_dt"] and center == configs["center_freq"] and bw == configs[
        "bandwidth"] and duration == configs["duration"] and ref_level == configs["ref_level"]


def _push_configs_node(dt: datetime, center: float, bw: float, duration: int, ref_level: float, node: int,
                       lora_dev: LoraSerial, max_attempts: int):
    attempts = 0
    while attempts < max_attempts:
        try:
            lora_dev.send_node_configs(node, folder_dt=dt, bandwidth=bw, center_freq=center, duration=duration,
                                       ref_level=ref_level)
        except TimeoutError:
            attempts += 1
        else:
            if not _check_configs(dt, center, bw, duration, ref_level, node, lora_dev):
                attempts += 1
            else:
                break

    if attempts >= max_attempts:
        print("Unable to configure nodes for next run")
        exit(1)


def _push_configs(dt: datetime, center: float, bw: float, duration: int, ref_level: float, nodes: set[int],
                  lora_dev: LoraSerial):
    max_attempts = 5
    for node in nodes:
        _push_configs_node(dt, center, bw, duration, ref_level, node, lora_dev, max_attempts)


def _indicate_run_ready_node(node: int, lora_dev: LoraSerial, max_attempts: int):
    attempts = 0
    while attempts < max_attempts:
        try:
            lora_dev.notify_run_ready(False, node)
        except TimeoutError:
            attempts += 1
        else:
            break

    if attempts >= max_attempts:
        print("Failed to notify that the run is ready")
        exit(1)


def _indicate_run_ready(nodes: set[int], lora_dev: LoraSerial):
    max_attempts = 5
    for node in nodes:
        _indicate_run_ready_node(node, lora_dev, max_attempts)


def _collect_polling(lora_port: Path,
                     center: float | None,
                     bandwidth: float | None,
                     duration: int | None,
                     ref_level: float | None,
                     gps_ts: bool,
                     quiet: bool,
                     poll_ids: tuple[int, ...]):
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

    # This is just here for the error message
    _ = _get_save_path(datetime.now())
    lora_dev = LoraSerial(LoraSerialConfig(port=str(lora_port)))
    lora_dev.start_driver()
    poll_ids_set = set(poll_ids)
    rx_dev = AresReceiverPolling(lora_dev, gps_ts, 10, poll_ids_set, poll_cb=_poll_results)

    run: bool = True

    while run:
        folder_dt = datetime.now()
        _push_configs(folder_dt, center, bandwidth, duration, ref_level, poll_ids_set, lora_dev)
        _indicate_run_ready(poll_ids_set, lora_dev)
        unique_save_path = _get_save_path(folder_dt)
        unique_save_path.mkdir()
        save_path = unique_save_path / f"rx{rx_dev.node_id}"
        try:
            print(f"Saving to {save_path}")
            rx_dev.start()
            rx_dev.stream_data(center, bandwidth, timedelta(seconds=duration), save_path, ref_level, quiet,
                               continue_callback=confirm)
        except KeyboardInterrupt:
            print("No data captured")
            shutil.rmtree(unique_save_path)
        rx_dev.stop()
        lora_dev.reboot(5)
        run = confirm("Start another run with the same parameters")
        lora_dev.start_driver()


def collect(
        lora_port: Path,
        /,
        center: float | None = None,
        bandwidth: float | None = None,
        duration: int | None = None,
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
        ref_level: The duration of the run.
        gps_ts: Use GPS timestamping.
        quiet: Run in quiet mode.
        now: Start measurement now.
        poll_ids: The node IDs to poll for. This will also designate the node as the polling node.
    """

    if poll_ids:
        _collect_polling(lora_port, center, bandwidth, duration, ref_level, gps_ts, quiet, poll_ids)
    elif not now:
        _collect_non_polling(lora_port, gps_ts, quiet)
    else:
        _collect_now_cmd(lora_port, center, bandwidth, duration, ref_level, gps_ts, quiet)

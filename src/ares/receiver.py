from ares_iq.signal_hound import SM200C, SM435C, SmConfigs, GpsModel, sm_get_device_list, SmDevice, GpsState, \
    SmDeviceType, SmStartTime
from ares_lora import LoraSerial, LoraException, LoraSerialConfig, LoraConfig, LoraLedState, LoraCodingRate, \
    LoraSpreadingFactor, LoraBandwidth, SettingId
import threading
from datetime import timedelta
from pathlib import Path
import logging
from weakref import WeakSet
from typing import Callable
import ares_iq_ext
from contextlib import contextmanager

logger = logging.getLogger("ares_receiver")
_instances = WeakSet()


def _shutdown_receivers():
    global _instances
    for x in _instances:
        x._threading_exit_func()


threading._register_atexit(_shutdown_receivers)


class AbortException(Exception):
    pass


@contextmanager
def acquire_lock(lock: threading.Lock, timeout: float = -1):
    result = lock.acquire(timeout=timeout)
    try:
        yield result
    finally:
        if result:
            lock.release()


class AresReceiver:
    def __init__(self,
                 lora_port: str,
                 gps_timestamping: bool,
                 model: GpsModel = GpsModel.PORTABLE,
                 start_notif_cb: Callable[[int, int], None] | None = None):
        """Initialize the AresReceiver instance.

        Args:
            lora_port: The serial port ares lora is on.
            gps_timestamping: Use GPS timestamping for the timebase.
            model: The GPS model to use. Default model used is PORTABLE.
        """
        lora_configs = LoraSerialConfig(
            port=lora_port,
            start_callback=self._lora_start_cb,
            poll_callback=self._poll_callback,
        )

        self._lora_dev = LoraSerial(lora_configs)
        self._lora_dev.set_logging_level(10)
        self._lora_dev.start_driver()
        self._dev_ready = threading.Event()

        self._lora_tx_lock = threading.Lock()

        # sm_class = self._get_dev_class()
        # self._sm_dev = sm_class(SmConfigs(gps_model=model.value))
        # self._sm_dev.open()
        self._gps_timestamping = gps_timestamping

        self._start_signal = threading.Event()
        self._start_time_sec: int = 0
        self._start_time_usec: int = 0

        self._start_notif: Callable[[int, int], None] | None = start_notif_cb

    @staticmethod
    def _get_dev_class() -> type[SM200C | SM435C]:
        devices = sm_get_device_list(usb=False, max_network_devices=1)
        if devices:
            if devices[0].type == SmDeviceType.SM200C:
                return SM200C
            if devices[0].type == SmDeviceType.SM435C:
                return SM435C
        raise OSError("No SM device found")

    def _lora_start_cb(self, seconds: int, microseconds: int):
        if self._dev_ready.is_set():
            self._start_time_sec = seconds
            self._start_time_usec = microseconds
            self._start_signal.set()

    @staticmethod
    def _poll_callback(src: int):
        logger.debug(f"Received poll event from {src}")

    def _stream_data(self, center: float, bw: float, duration: timedelta, save_directory: str | Path,
                     silent: bool = True, chunk_size: int = int(4e9)):
        self._lora_dev.ready = True
        self._lora_dev.led(1, LoraLedState.BLINK)
        self._start_signal.wait()
        if self._start_notif is not None:
            self._start_notif(self._start_time_sec, self._start_time_usec)
        with self._lora_tx_lock:
            self._start_signal.clear()
            self._lora_dev.led(1, LoraLedState.ON)
            self._sm_dev.stream_iq(center, bw, chunk_size, duration, save_directory,
                                   start_time=SmStartTime(self._start_time_sec, self._start_time_usec), silent=silent)
            self._sm_dev.abort_measurement()

    def stream_data(self, center: float, bw: float, duration: timedelta, save_directory: str | Path,
                    silent: bool = True, chunk_size: int = int(4e9), now: bool = False, **kwargs):
        """Wait for the start signal for collecting data and collect data.

        Args:
            now:
            chunk_size:
            silent:
            center: The center frequency.
            bw: The bandwidth.
            duration: The capture duration of the data.
            save_directory: The directory path to save the data to.
        """
        if self._gps_timestamping:
            self._sm_dev.enable_gps_timestamping(True)

        if now:
            self._sm_dev.stream_iq(center, bw, chunk_size, duration, save_directory, silent=silent)
            self._sm_dev.abort_measurement()
            return

        self._dev_ready.set()

        try:
            self._stream_data(center, bw, duration, save_directory, silent, chunk_size)
        finally:
            self._lora_dev.ready = False
            self._lora_dev.led(1, LoraLedState.OFF)
            self._dev_ready.clear()

    def capture_live_data(self, center: float, bw: float, capture_size: int = int(4e9), silent: bool = False,
                          verbose: bool = False):
        """Capture an I/Q data live shot with a specified capture size.

        Args:
            center: The center frequency of the capture.
            bw: The bandwidth of the capture.
            capture_size: The amount of bytes to capture.
            silent: Do not show progress bar.
            verbose: Show logging messages.

        Returns:
            The captured IQ data
        """

        if self._gps_timestamping:
            self._sm_dev.enable_gps_timestamping(True)

        iq, _, _ = self._sm_dev.capture_iq(center, bw, capture_size, silent, verbose)
        return iq

    def _cleanup(self):
        if hasattr(self, '_sm_dev'):
            if isinstance(self._sm_dev, (SM200C, SM435C)):
                self._sm_dev.close()
        try:
            self._lora_dev.stop_driver()
        except RuntimeError:
            pass

    @property
    def node_id(self):
        ret = self._lora_dev.setting(SettingId.ID)
        if ret is None:
            raise RuntimeError("Setting return value is `None`")
        if ret == 0:
            raise ValueError("ID setting not valid")
        return ret - 1

    @property
    def sample_rate(self):
        return self._sm_dev.sample_rate

    @property
    def ref_level(self):
        return self._sm_dev.ref_level

    def __del__(self):
        self._cleanup()


class AresReceiverPolling:
    def __init__(self, lora_port: str, gps_timestamping: bool, poll_period: float, valid_node_ids: set[int],
                 model: GpsModel = GpsModel.PORTABLE, poll_cb: Callable[[dict[int, bool]], None] | None = None,
                 start_notif_cb: Callable[[int, int], None] | None = None):
        lora_configs = LoraSerialConfig(
            port=lora_port,
            log_callback=self._lora_log_callback
        )
        self._lora_dev = LoraSerial(lora_configs)
        self._lora_dev.set_logging_level(10)
        self._lora_dev.start_driver()

        self._poll_period = poll_period
        # Make things make sense. Since 0 is invalid for a node ID, things are incremented by 1
        self._poll_ids: dict[int, bool] = {poll_id + 1: False for poll_id in valid_node_ids}
        self._poll_devs_ready = threading.Event()
        self._poll_thread_not_running = threading.Event()
        self._poll_thread_not_running.set()
        self._poll_thread: threading.Thread | None = None

        sm_class = self._get_dev_class()
        self._sm_dev: SM200C | SM435C = sm_class(SmConfigs(gps_model=model.value))
        self._sm_dev.open()
        self._gps_timestamping = gps_timestamping

        self._lora_tx_lock = threading.Lock()

        self._self_ready = threading.Event()
        node_id = self._lora_dev.setting(SettingId.ID)
        assert isinstance(node_id, int)
        self._node_id: int = node_id - 1
        self._poll_cb = poll_cb

        self._start_cb = start_notif_cb

    def _lora_log_callback(self, src_id: int, message: str):
        pass

    @staticmethod
    def _get_dev_class() -> type[SM200C | SM435C]:
        devices = sm_get_device_list(usb=False, max_network_devices=1)
        if devices:
            if devices[0].type == SmDeviceType.SM200C:
                return SM200C
            if devices[0].type == SmDeviceType.SM435C:
                return SM435C
        raise OSError("No SM device found")

    def _poll_node(self, node_id: int) -> bool | None:
        ret = False
        with acquire_lock(self._lora_tx_lock, 2) as acquired:
            if not acquired:
                return None
            try:
                ret = self._lora_dev.send_poll(node_id)
            except TimeoutError as e:
                if str(e) != "Timed out waiting for a heartbeat response":
                    logger.error(e)
        return ret

    def _call_user_poll_cb(self):
        if self._poll_cb is not None:
            param: dict[int, bool] = {node_id - 1: node_ready for node_id, node_ready in self._poll_ids.items()}
            param[self._node_id] = self._self_ready.is_set()
            self._poll_cb(param)

    def _poll_thread_handler(self):
        timeout = 0
        while not self._poll_thread_not_running.wait(timeout):
            timeout = self._poll_period
            for poll_id in self._poll_ids.keys():
                result = self._poll_node(poll_id)
                if result is not None:
                    self._poll_ids[poll_id] = result
            if all(self._poll_ids.values()):
                self._poll_devs_ready.set()
            self._call_user_poll_cb()

    def _threading_exit_func(self):
        self._stop()

    def _stop(self):
        self._poll_thread_not_running.set()

    def _cleanup(self):
        self._stop()
        if hasattr(self, '_sm_dev'):
            if isinstance(self._sm_dev, (SM200C, SM435C)):
                self._sm_dev.close()
        try:
            self._lora_dev.stop_driver()
        except RuntimeError:
            pass

    def __del__(self):
        self._cleanup()

    def start(self):
        if not self._poll_thread_not_running.is_set():
            raise RuntimeError("Already running")
        self._poll_thread_not_running.clear()
        self._poll_thread = threading.Thread(target=self._poll_thread_handler)
        assert isinstance(self._poll_thread, threading.Thread)
        self._poll_thread.start()

        global _instances
        _instances.add(self)

    def stop(self):
        if self._poll_thread_not_running.is_set():
            raise RuntimeError("already stopped")
        self._stop()

        if self._poll_thread is not None:
            self._poll_thread.join(20.0)
            self._poll_thread = None

        global _instances
        if self in _instances:
            _instances.remove(self)

    @property
    def node_id(self):
        ret = self._lora_dev.setting(SettingId.ID)
        if ret is None:
            raise RuntimeError("setting return value is `None`")
        if ret == 0:
            raise ValueError("ID setting not valid")
        return ret - 1

    def _start(self, start_delay_sec: int, start_delay_usec: int) -> tuple[int, int]:
        self._lora_dev.led(1, LoraLedState.ON)
        start_usec = 0
        if self._gps_timestamping:
            sm_gps = self._sm_dev.get_gps_info(True)
            start_sec = sm_gps.sec_since_epoch + start_delay_sec
        else:
            start_sec, start_usec = ares_iq_ext.add_time(*ares_iq_ext.time_now(), start_delay_sec, start_delay_usec)
        self._lora_dev.start(start_sec, start_usec)

        if self._start_cb is not None:
            self._start_cb(start_sec, start_usec)

        return start_sec, start_usec

    def _stream_data(self, center: float, bw: float, duration: timedelta, save_directory: str | Path,
                     silent: bool = True, chunk_size: int = int(4e9), start_delay_sec: int = 30, start_delay_usec: int = 0, continue_callback: Callable[[str], bool] | None = None):
        self._lora_dev.led(1, LoraLedState.BLINK)
        self._poll_devs_ready.wait()
        with self._lora_tx_lock:
            if continue_callback is not None:
                ret = continue_callback("Start the measurement")
                if not ret:
                    raise AbortException()

            start_sec, start_usec = self._start(start_delay_sec, start_delay_usec)
            self._sm_dev.stream_iq(center, bw, chunk_size, duration, save_directory, silent=silent,
                                   start_time=SmStartTime(second=start_sec, microsecond=start_usec))
            self._sm_dev.abort_measurement()

    def stream_data(self, center: float, bw: float, duration: timedelta, save_directory: str | Path,
                    silent: bool = True, chunk_size: int = int(4e9), now: bool = False, continue_callback: Callable[[str], bool] | None = None):
        if self._gps_timestamping:
            self._sm_dev.enable_gps_timestamping(True)

        if now:
            self._sm_dev.stream_iq(center, bw, chunk_size, duration, save_directory, silent=silent)
            self._sm_dev.abort_measurement()
            return

        self._self_ready.set()

        try:
            self._stream_data(center, bw, duration, save_directory, silent, chunk_size, continue_callback=continue_callback)
        finally:
            self._lora_dev.led(1, LoraLedState.OFF)
            self._self_ready.clear()

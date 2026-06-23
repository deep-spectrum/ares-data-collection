from ares_iq.signal_hound import SM200C, SM435C, SmConfigs, GpsModel, sm_get_device_list, SmDevice, GpsState, \
    SmDeviceType, SmStartTime
from ares_lora import LoraSerial, LoraException, LoraSerialConfig, LoraConfig, LoraLedState, LoraCodingRate, \
    LoraSpreadingFactor, LoraBandwidth
import threading
import time
from datetime import timedelta
from pathlib import Path
import logging
from weakref import WeakSet
import random

logger = logging.getLogger("ares_receiver")
_instances = WeakSet()


def _shutdown_receivers():
    global _instances
    for x in _instances:
        x._stop()


threading._register_atexit(_shutdown_receivers)


class AresReceiver:
    def __init__(self, lora_port: str, gps_timestamping: bool, model: GpsModel = GpsModel.PORTABLE, heartbeat_lower: float = 30, heartbeat_upper: float = 60):
        """Initialize the AresReceiver instance.

        Args:
            lora_port: The serial port ares lora is on.
            gps_timestamping: Use GPS timestamping for the timebase.
            model: The GPS model to use. Default model used is PORTABLE.
        """
        lora_configs = LoraSerialConfig(
            port=lora_port,
            start_callback=self._lora_start_cb,
            claim_callback=self._lora_claim_event
        )

        if heartbeat_lower >= heartbeat_upper:
            raise AttributeError("Lower bound must be smaller than upper bound")

        self._heartbeat_lower = heartbeat_lower
        self._heartbeat_upper = heartbeat_upper

        self._lora_dev = LoraSerial(lora_configs)
        self._lora_dev.start_driver()
        self._dev_ready = threading.Event()
        self._heartbeat_lock = threading.Lock()
        self._heartbeat_running = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None
        self._heartbeat_strobe_cnt = 3

        sm_class = self._get_dev_class()
        self._sm_dev = sm_class(SmConfigs(gps_model=model.value))
        self._sm_dev.open()
        self._gps_timestamping = gps_timestamping

        self._start_signal = threading.Event()
        self._start_time_sec: int = 0
        self._start_time_usec: int = 0

    @staticmethod
    def _get_dev_class() -> type[SM200C | SM435C]:
        devices = sm_get_device_list(usb=False, max_network_devices=1)
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

    def _lora_heartbeat(self):
        while self._heartbeat_running.is_set():
            sleep_time = random.uniform(self._heartbeat_lower, self._heartbeat_upper)
            time.sleep(sleep_time)
            with self._heartbeat_lock:
                ready = self._dev_ready.is_set()
                try:
                    self._lora_dev.send_heartbeat(ready, strobe_count=self._heartbeat_strobe_cnt)
                except TimeoutError:
                    print("Timeout error occurred")

    def _lora_claim_event(self, host_id: int):
        self._heartbeat_strobe_cnt = 1

    def capture_data(self, center: float, bw: float, duration: timedelta, save_directory: str | Path, silent: bool = True):
        """Wait for the start signal for collecting data and collect data.

        Args:
            center: The center frequency.
            bw: The bandwidth.
            duration: The capture duration of the data.
            save_directory: The directory path to save the data to.
        """
        if self._gps_timestamping:
            self._sm_dev.enable_gps_timestamping(True)
        self._dev_ready.set()

        self._start_signal.wait()

        with self._heartbeat_lock:
            self._start_signal.clear()
            self._sm_dev.stream_iq(center, bw, int(4e9), duration, save_directory,
                                   start_time=SmStartTime(self._start_time_sec, self._start_time_usec), silent=silent)
            self._dev_ready.clear()
            self._sm_dev.abort_measurement()

    def start(self):
        """Start the receiver background tasks and make the node visible to the world."""
        if self._heartbeat_running.is_set():
            raise RuntimeError("Already running")
        self._heartbeat_running.set()
        self._heartbeat_thread = threading.Thread(target=self._lora_heartbeat)
        assert isinstance(self._heartbeat_thread, threading.Thread)
        self._heartbeat_thread.start()

        global _instances
        _instances.add(self)

    def _stop(self):
        self._heartbeat_running.clear()

    def stop(self):
        """Stop the receiver background tasks."""
        if not self._heartbeat_running.is_set():
            raise RuntimeError("Already stopped")
        self._stop()

        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(20.0)
            self._heartbeat_thread = None

        global _instances
        if self in _instances:
            _instances.remove(self)

    def _cleanup(self):
        self._stop()
        self._sm_dev.close()
        try:
            self._lora_dev.stop_driver()
        except RuntimeError:
            pass

    def __del__(self):
        self._cleanup()

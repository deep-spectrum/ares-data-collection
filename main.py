from ares_iq.signal_hound import SM200C, SM435C, SmConfigs, GpsModel, sm_get_device_list, SmDevice, GpsState, SmDeviceType
from ares_lora import LoraSerial, LoraException, LoraSerialConfig, LoraConfig, LoraLedState, LoraCodingRate, \
    LoraSpreadingFactor, LoraBandwidth
import threading
import time
from datetime import timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, Future
import logging


class AresReceiver:
    def __init__(self, lora_port: str, gps_stamping: bool, model: GpsModel = GpsModel.STATIONARY):
        lora_configs = LoraSerialConfig(
            port=lora_port,
            start_callback=self._lora_start_cb
        )

        self._lora_dev = LoraSerial(lora_configs)
        self._lora_dev.set_logging_level(logging.DEBUG)
        self._lora_dev.start_driver()
        self._dev_ready = threading.Event()
        self._heartbeat_lock = threading.Lock()
        self._heartbeat_running = False

        sm_class = self._get_dev_class()
        self._sm_dev = sm_class(SmConfigs(gps_model=model.value))
        self._sm_dev.set_log_level(logging.DEBUG)
        self._sm_dev.open()
        self._gps_stamping = gps_stamping

        self._tasks: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=2)
        self._lora_heartbeat_future: Future[None] | None = None

        self._start_signal = threading.Event()
        self._start_time_sec: int = 0
        self._start_time_ns: int = 0

    @staticmethod
    def _get_dev_class() -> type[SM200C | SM435C]:
        devices = sm_get_device_list(usb=False, max_network_devices=1)
        if devices[0].type == SmDeviceType.SM200C:
            print("SM200C found")
            return SM200C
        elif devices[0].type == SmDeviceType.SM435C:
            print("SM435C found")
            return SM435C
        else:
            raise RuntimeError("SM device not found")

    def _lora_heartbeat(self):
        while self._heartbeat_running:
            with self._heartbeat_lock:
                ready = self._dev_ready.is_set()
                self._lora_dev.send_heartbeat(ready)
            time.sleep(1.0)

    def _lora_start_cb(self, seconds: int, nanoseconds: int):
        self._start_time_sec = seconds
        self._start_time_ns = nanoseconds
        self._start_signal.set()

    def capture_data(self, center: float, bw: float, duration: timedelta, save_directory: str | Path):
        if self._gps_stamping:
            self._sm_dev.enable_gps_timestamping(True)
        self._dev_ready.set()

        self._start_signal.wait()

        with self._heartbeat_lock:
            self._sm_dev.stream_iq(center, bw, int(4e9), duration, save_directory, gps_start_time=self._start_time_sec)
            self._dev_ready.clear()
        
        self._start_signal.clear()

    def start(self):
        if self._heartbeat_running:
            raise RuntimeError("Already running")
        self._heartbeat_running = True
        self._lora_heartbeat_future = self._tasks.submit(self._lora_heartbeat)

    def stop(self):
        if not self._heartbeat_running:
            raise RuntimeError("already stopped")
        self._heartbeat_running = False
        assert self._lora_heartbeat_future is not None
        self._lora_heartbeat_future.result()

    def __del__(self):
        try:
            self.stop()
        except RuntimeError:
            pass
        self._tasks.shutdown()
        self._sm_dev.close()
        self._lora_dev.stop_driver()

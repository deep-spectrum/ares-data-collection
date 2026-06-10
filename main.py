from ares_iq.signal_hound import SM200C, SM435C, SmConfigs, GpsModel, sm_get_device_list, SmDevice, GpsState, SmDeviceType
from ares_lora import LoraSerial, LoraException, LoraSerialConfig, LoraConfig, LoraLedState, LoraCodingRate, \
    LoraSpreadingFactor, LoraBandwidth
import threading
import time
from datetime import timedelta, datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, Future
import logging
from dataclasses import dataclass
import ares_iq_ext

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
        # self._lora_dev.set_logging_level(logging.WARNING)

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


@dataclass
class AresNode:
    ready: bool
    last_update: datetime


class AresTransmitter:

    def __init__(self, lora_port: str, gps_stamping: bool, node_timeout: timedelta):
        lora_configs = LoraSerialConfig(port=lora_port, master=True, heartbeat_callback=self._heartbeat_callback)
        self._nodes: dict[int, AresNode] = {}
        self._gps_timestamping = gps_stamping
        self._neighbor_lock = threading.Lock()

        self._timeout = node_timeout
        self._running_node_list_manager = True

        self._lora_dev = LoraSerial(lora_configs)
        self._lora_dev.set_logging_level(logging.DEBUG)

        self._tasks: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=2)
        self._node_manager_future: Future[None] = self._tasks.submit(self._neighbor_manager)

        self._lora_dev.start_driver()

    def _heartbeat_callback(self, node_id: int, ready: bool):
        with self._neighbor_lock:
            if node_id not in self._nodes:
                print("Adding node", node_id)
            self._nodes[node_id] = AresNode(ready, datetime.now())

    def _neighbor_manager(self):
        while self._running_node_list_manager:
            nodes_to_remove = []
            with self._neighbor_lock:
                for node_id, meta in self._nodes.items():
                    timedelta_since_last_update = datetime.now() - meta.last_update
                    if timedelta_since_last_update > self._timeout:
                        nodes_to_remove.append(node_id)
                for node_id in nodes_to_remove:
                    del self._nodes[node_id]
            time.sleep(2.0)



    def start(self, start_delay_sec: int, start_delay_usec: int):
        if start_delay_sec < 0 or start_delay_usec < 0:
            raise ValueError("start delay values cannot be negative")

        now_sec, now_usec = ares_iq_ext.time_now()
        start_sec, start_usec = ares_iq_ext.add_time(now_sec, now_usec, start_delay_sec, start_delay_usec)

        self._lora_dev.start(start_sec, start_usec)

    def __del__(self):
        self._lora_dev.stop_driver()
        self._running_node_list_manager = False
        self._node_manager_future.result()
        self._tasks.shutdown()


if __name__ =='__main__':
    x = AresTransmitter('/dev/ttyACM1', False, timedelta(seconds=30))
    time.sleep(10.0)


from ares_lora import LoraSerial, LoraException, LoraSerialConfig, LoraConfig, LoraLedState, LoraCodingRate, \
    LoraSpreadingFactor, LoraBandwidth
import threading
from datetime import timedelta, datetime
import logging
from dataclasses import dataclass
import ares_iq_ext
from copy import deepcopy
from weakref import WeakSet
from typing import Callable

logger = logging.getLogger("ares_transmitter")

_instances = WeakSet()


def _shutdown_transmitters():
    global _instances
    for x in _instances:
        x._shutdown_manager_thread()


threading._register_atexit(_shutdown_transmitters)


@dataclass
class AresNode:
    """Node metadata.

    Attributes:
        ready: Flag indicating if the node is ready to collect data.
        last_update: Last datetime recorded since the last update.
    """
    ready: bool
    last_update: datetime


class AresTransmitter:
    """
    Ares EW Data collection system transmitter abstraction.
    """

    def __init__(self, lora_port: str, gps_timestamping: bool, node_timeout: timedelta,
                 start_notif_cb: Callable[[int, int], None] | None = None):
        """Initialize the AresTransmitter instance.

        Args:
            lora_port: The serial port ares lora is on.
            gps_timestamping: Use GPS timestamping for the timebase.
            node_timeout: The amount of time allowed to elapse before removing a node from the list.
        """
        self._nodes: dict[int, AresNode] = {}
        self._gps_timestamping = gps_timestamping
        self._neighbors_lock = threading.Lock()

        self._timeout = node_timeout
        self._node_manager_not_running = threading.Event()

        lora_configs = LoraSerialConfig(port=lora_port, master=True, heartbeat_callback=self._heartbeat_callback)
        self._lora_dev = LoraSerial(lora_configs)

        self._neighbor_manager = threading.Thread(target=self._neighbor_manager_handle)
        self._neighbor_manager.start()

        self._lora_dev.start_driver()

        self._start_notif_cb = start_notif_cb

        global _instances
        _instances.add(self)

    def _heartbeat_callback(self, node_id: int, ready: bool):
        with self._neighbors_lock:
            if node_id not in self._nodes:
                logger.debug(f"Adding {node_id} to list")
            self._nodes[node_id] = AresNode(ready, datetime.now())

    def _neighbor_manager_handle(self):
        while not self._node_manager_not_running.wait(2.0):
            nodes_to_remove = []
            with self._neighbors_lock:
                for node_id, meta in self._nodes.items():
                    timedelta_since_update = datetime.now() - meta.last_update
                    if timedelta_since_update > self._timeout:
                        nodes_to_remove.append(node_id)
                for node_id in nodes_to_remove:
                    logger.debug(f"Removing {node_id} from list")
                    del self._nodes[node_id]

    def start(self, start_delay_sec: int, start_delay_usec: int = 0):
        """Start IQ measurements after a specified delay.

        Args:
            start_delay_sec: The amount of seconds to add to the start time.
            start_delay_usec: The amount of microseconds to add to the start time. Ignored if GPS timestamping is enabled.
        """
        if start_delay_sec < 0 or start_delay_usec < 0:
            raise ValueError("start delay values cannot be negative")

        if self._gps_timestamping:
            raise NotImplementedError("GPS timestamps have not been implemented yet")
        else:
            start_sec, start_usec = ares_iq_ext.add_time(*ares_iq_ext.time_now(), start_delay_sec, start_delay_usec)

        self._lora_dev.start(start_sec, start_usec)

        if self._start_notif_cb is not None:
            self._start_notif_cb(start_sec, start_usec)

    @property
    def nodes(self):
        """The nodes emitting heartbeats."""
        with self._neighbors_lock:
            ret = deepcopy(self._nodes)
        return ret

    def _shutdown_manager_thread(self):
        self._node_manager_not_running.set()
        if self._neighbor_manager is not None:
            self._neighbor_manager.join(10.0)
            self._neighbor_manager = None

    def _shutdown(self):
        self._shutdown_manager_thread()
        self._lora_dev.stop_driver()

        global _instances
        if self in _instances:
            _instances.remove(self)

    def __del__(self):
        self._shutdown()

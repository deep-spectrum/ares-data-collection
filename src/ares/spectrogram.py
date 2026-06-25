from __future__ import annotations

import numpy as np
import numpy.typing as npt
import matplotlib.pyplot as plt
import enum
from dataclasses import dataclass
from pathlib import Path


class Window(enum.Enum):
    HANNING = enum.auto()
    HAMMING = enum.auto()
    BLACKMAN = enum.auto()
    RECT = enum.auto()


@dataclass
class SpectrogramParameters:
    file_name: Path
    center: float
    bandwidth: float
    ref_level: float
    sample_rate: float

    nfft: int = 1024
    window: Window = Window.HAMMING
    colormap: str = 'jet'
    max_rows: int = 1000


def _build_window(params: SpectrogramParameters) -> npt.NDArray[np.float64]:
    match params.window:
        case Window.HAMMING:
            return np.hamming(params.nfft).astype(np.float64)
        case Window.HANNING:
            return np.hanning(params.nfft).astype(np.float64)
        case Window.BLACKMAN:
            return np.blackman(params.nfft).astype(np.float64)
        case Window.RECT:
            return np.ones(params.nfft).astype(np.float64)
    raise RuntimeError("Unreachable")


def build_spectrogram(iq_data, ts, params):
    """Build the spectrogram from the recorded data.

    Args:
        iq_data: The recorded I/Q data
        ts: The timestamps of each row
        params: Additional parameters

    Returns:

    """
    window = _build_window(params)
    win_norm = float(np.sum(window)) ** 2
    eps = 1e-20


def generate_spectrogram(iq_data: npt.NDArray[np.complex64], ts: npt.NDArray[np.float64], params: SpectrogramParameters):
    pass

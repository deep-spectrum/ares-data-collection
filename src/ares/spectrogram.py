from __future__ import annotations

import numpy as np
import numpy.typing as npt
import matplotlib
import matplotlib.pyplot as plt
import enum
from dataclasses import dataclass
from pathlib import Path
import time


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
    node_id: int | None = None
    show: bool = False
    dpi: float = 120


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


def _check_shapes(iq_data: npt.NDArray[np.complex64], ts: npt.NDArray[np.float64]):
    if len(iq_data.shape) != 2:
        raise ValueError("I/Q Data must be a 2D array")
    if len(ts.shape) != 1:
        raise ValueError("Timestamps must be a 1D array")
    if iq_data.shape[0] != ts.shape[0]:
        raise ValueError("There must be as many timestamps as I/Q captures")


def _interpolate_timestamps(iq_data: npt.NDArray[np.complex64], ts: npt.NDArray[np.float64],
                            params: SpectrogramParameters):
    samples_per_capture = iq_data.shape[1]
    total_samples = iq_data.shape[0] * iq_data.shape[1]
    interval = params.nfft
    total_captures = iq_data.shape[0]

    capture_starts = (
            np.arange(total_captures, dtype=np.float64) * samples_per_capture
    )

    n = total_samples // interval
    interval_starts = np.arange(n, dtype=np.float64) * interval
    timestamps = np.interp(
        interval_starts, capture_starts, ts
    )

    return timestamps


def _build_spectrogram(iq_data: npt.NDArray[np.complex64], ts: npt.NDArray[np.float64], params: SpectrogramParameters):
    """Build the spectrogram from the recorded data.

    Args:
        iq_data: The recorded I/Q data
        ts: The timestamps of each row
        params: Additional parameters

    Returns:

    """

    iq_data_flat = iq_data.flatten()

    def read_frames(f_start: int, n_frames: int) -> npt.NDArray[np.complex64]:
        count = n_frames * params.nfft
        out = np.empty(count, dtype=np.complex64)
        written = 0
        pos = f_start * params.nfft
        total_samples = iq_data.shape[0] * iq_data.shape[1]

        while written < count:
            chunk_idx = pos // total_samples
            offset = pos % total_samples
            chunk_samples = min(total_samples, total_samples - chunk_idx * total_samples)
            to_read = min(count - written, chunk_samples - offset)
            out[written: written + to_read] = iq_data_flat[offset: offset + to_read]
            written += to_read
            pos += to_read
        return out.reshape(n_frames, params.nfft)

    window = _build_window(params)
    win_norm = float(np.sum(window)) ** 2
    eps = 1e-20

    frames = (iq_data.shape[0] * iq_data.shape[1]) // params.nfft
    rows = min(frames, params.max_rows)
    stride = frames / rows

    t0 = float(ts[0]) if len(ts) else 0.0

    spec = np.empty((rows, params.nfft), dtype=np.float32)
    time_s = np.empty(rows, dtype=np.float64)

    for r in range(rows):
        f0 = int(r * stride)
        f1 = max(int((r + 1) * stride), f0 + 1)
        time_s[r] = float(ts[f0]) - t0 if len(ts) else f0 * params.nfft / params.sample_rate

        acc = np.zeros(params.nfft, dtype=np.float32)
        nfr = f1 - f0
        read = 0
        while read < nfr:
            b = min(4096, nfr - read)
            block = read_frames(f0 + read, b)
            acc += (np.abs(np.fft.fft(block * window, axis=1)) ** 2).sum(axis=0)
            read += b
        power = acc / nfr
        spec[r] = 10.0 * np.log10(np.fft.fftshift(power) / win_norm + eps)

    bins = np.fft.fftshift(np.fft.fftfreq(params.nfft, d=1.0 / params.sample_rate))
    freq_hz = params.center + bins
    return spec, freq_hz, time_s


def _trim_band(spec: npt.NDArray[np.float32], freq_hz: npt.NDArray[np.float64], params: SpectrogramParameters):
    lo = params.center - (params.bandwidth / 2)
    hi = params.center + (params.bandwidth / 2)
    keep = (freq_hz >= lo) & (freq_hz <= hi)
    n_keep = int(keep.sum())
    if n_keep < 2 or n_keep == len(freq_hz):
        return spec, freq_hz
    return spec[:, keep], freq_hz[keep]


def _plot(spec, freq_hz, time_s, abs_start_epoch, params: SpectrogramParameters):
    if not params.show:
        matplotlib.use("Agg")

    f = freq_hz / 1e6
    df = (freq_hz[1] - freq_hz[0]) if len(freq_hz) > 1 else 0.0
    f_lo = f[0]
    f_hi = (freq_hz[-1] + df) / 1e6

    vmax = params.ref_level
    vmin = params.ref_level - 100

    fig, ax = plt.subplots(figsize=(10, 7))
    im = ax.imshow(
        spec, aspect="auto",
        origin="upper",
        cmap=params.colormap,
        vmin=vmin,
        vmax=vmax,
        extent=[f_lo, f_hi, time_s[-1], time_s[0]],
        interpolation="nearest",
    )
    ax.set_xlabel("Frequency (MHz)")
    ax.set_ylabel("Time (s)")
    cbar = fig.colorbar(im, ax=ax, pad=0.02)
    cbar.set_label("Power (dB)")

    if abs_start_epoch is not None:
        start_time_title = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(abs_start_epoch))
    else:
        start_time_title = "Unknown"

    if params.node_id is not None:
        title = f"Ares {params.node_id} Spectrogram\nStart {start_time_title}  |  nfft {params.nfft}"
    else:
        title = f"Spectrogram\nStart {start_time_title}  |  nfft {params.nfft}"

    ax.set_title(title, fontsize=10)
    fig.tight_layout()
    fig.savefig(params.file_name, dpi=params.dpi)

    if params.show:
        plt.show()
    plt.close(fig)


def generate_spectrogram(iq_data: npt.NDArray[np.complex64], ts: npt.NDArray[np.float64],
                         params: SpectrogramParameters):
    _check_shapes(iq_data, ts)

    timestamps = _interpolate_timestamps(iq_data, ts, params)

    spec, freq_hz, time_s = _build_spectrogram(iq_data, timestamps, params)
    spec, freq_hz = _trim_band(spec, freq_hz, params)
    abs_start = float(timestamps[0])
    _plot(spec, freq_hz, time_s, abs_start, params)

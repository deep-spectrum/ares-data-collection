import tyro
from typing_extensions import Annotated
from ares.receiver import AresReceiver
from typing import Literal
from datetime import datetime
from pathlib import Path
from ares.spectrogram import SpectrogramParameters, generate_spectrogram, Window
from tempfile import TemporaryDirectory
import numpy as np
import shutil


def spot_check(
        lora_port: Path,
        center: float,
        bandwidth: float,
        capture_size: int = int(4e9),
        /,
        dpi: int = 120,
        nfft: int = 1024,
        window: Literal["hanning", "hamming", "blackman", "rect"] = "hamming",
        show: Annotated[bool, tyro.conf.FlagCreatePairsOff] = False,
        max_rows: int = 1000,
        colormap: Literal["jet"] = "jet",
        save_loc: Path | None = None,
):
    """Generate a spectrogram from live capture data.

    Args:
        lora_port: The lora port.
        center: The center frequency in Hz.
        bandwidth: The capture bandwidth in Hz.
        capture_size: The amount of bytes to capture.
        dpi: The image quality.
        nfft: Number of FFTs.
        window: The window to use.
        show: Show the image (GUI is needed).
        max_rows: Maximum amount of rows.
        colormap: The color map to use.
        save_loc: The save location of the generated image.
    """

    window_enum = {
        "hanning": Window.HANNING,
        "hamming": Window.HAMMING,
        "blackman": Window.BLACKMAN,
        "rect": Window.RECT,
    }

    rx = AresReceiver(str(lora_port), False)

    now = datetime.now()
    iq = rx.capture_live_data(center, bandwidth, capture_size)

    iq_data = np.vstack([iq_.iq for iq_ in iq], dtype=np.complex64)
    ts_data = np.array([iq_.ts.timestamp() for iq_ in iq], dtype=np.float64)

    with TemporaryDirectory() as temp:
        name = f"capture-{now.strftime('%Y-%m-%d-%H%M%S')}.png"
        file = Path(temp) / name

        params = SpectrogramParameters(
            file,
            center,
            bandwidth,
            rx.ref_level,
            rx.sample_rate,

            nfft=nfft,
            window=window_enum[window],
            colormap=colormap,
            max_rows=max_rows,
            node_id=rx.node_id,
            show=show,
            dpi=dpi,
        )

        generate_spectrogram(iq_data, ts_data, params)

        if save_loc is not None:
            shutil.copy(file, save_loc)
        else:
            pass
            # TODO: Enable BLE and push image over BLE

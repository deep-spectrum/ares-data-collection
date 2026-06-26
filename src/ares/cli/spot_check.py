import tyro
from typing_extensions import Annotated
from ares.receiver import AresReceiver
from typing import Literal
from datetime import timedelta, datetime
from pathlib import Path
from ares.spectrogram import SpectrogramParameters, generate_spectrogram, Window
from tempfile import TemporaryDirectory
import numpy as np


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

    window_enum = {
        "hanning": Window.HANNING,
        "hamming": Window.HAMMING,
        "blackman": Window.BLACKMAN,
        "rect": Window.RECT,
    }

    rx = AresReceiver(str(lora_port), False)

    now = datetime.now()
    iq = rx.capture_live_data(center, bandwidth, capture_size)

    iq_data = np.vstack([iq_.iq for iq_ in iq])
    ts_data = np.array([iq_.ts.timestamp() for iq_ in iq])

    print(iq_data)
    print(ts_data)

    # with TemporaryDirectory() as temp:
    #     name = f"capture {now.strftime('%Y-%m-%d-%H%M%S')}"
    #
    #     params = SpectrogramParameters(
    #         Path(temp) / name,
    #         center,
    #         bandwidth,
    #         -20,
    #         rx.sample_rate,
    #
    #         nfft=nfft,
    #         window=window_enum[window],
    #         colormap=colormap,
    #         max_rows=max_rows,
    #         node_id=rx.node_id,
    #         show=show,
    #         dpi=dpi,
    #     )
    #
    #
    #
    #     # generate_spectrogram(iq.)
    #
    #     if save_loc is not None:


"""Musical time: the tick grid the chart is written on."""
from __future__ import annotations

import numpy as np

from .params import RES


def metric_class(tick: int) -> int:
    """0 = downbeat (bar), 1 = beat, 2 = 8th, 3 = 16th. Assumes 4/4."""
    if tick % (4 * RES) == 0:
        return 0
    if tick % RES == 0:
        return 1
    if tick % (RES // 2) == 0:
        return 2
    return 3


class Grid:
    """Maps chart ticks to audio seconds.

    The audio is delayed by `pad` seconds so that the first detected beat lands exactly on a beat tick;
    `t[i]` is the (padded) time of tick `i * RES`. Times returned to callers are in the *original*
    (unpadded) audio timeline.
    """

    def __init__(self, beats: np.ndarray, period: float):
        beats = beats[beats > 0]
        self.pad = float((period - beats[0]) % period)
        if self.pad < 0.05:
            self.pad += period
        b = beats + self.pad
        head = np.arange(0, b[0] - period / 2, period)
        self.t = np.concatenate([head, b])
        self.k = np.arange(len(self.t)) * RES

    @property
    def bpm(self) -> float:
        return 60.0 / float(np.median(np.diff(self.t)))

    def slot_times(self, sub: int = 4):
        """(times, ticks) of every 1/sub-beat slot."""
        ticks = np.arange(0, self.k[-1], RES // sub)
        return np.interp(ticks, self.k, self.t) - self.pad, ticks

    def sync_lines(self, constant_bpm: float | None = None) -> list[str]:
        """[SyncTrack] lines: one tempo for click-track songs, otherwise a tempo change per beat."""
        lines = ["0 = TS 4"]
        if constant_bpm:
            return lines + [f"0 = B {int(round(constant_bpm * 1000))}"]
        last = None
        for i in range(len(self.t) - 1):
            bpm = int(round(60000.0 / max(self.t[i + 1] - self.t[i], 1e-3)))
            if bpm != last:
                lines.append(f"{i * RES} = B {bpm}")
                last = bpm
        return lines

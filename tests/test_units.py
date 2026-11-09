"""Fast unit tests: no models, no audio files needed."""
import os

import numpy as np
import pytest

from autochart import arrange, chart, chartio, sng
from autochart.grid import Grid, metric_class
from autochart.params import DEFAULT, RES
from autochart.pitch import fold_octaves, viterbi


def test_metric_class():
    assert [metric_class(k) for k in (0, RES, RES // 2, RES // 4, 4 * RES)] == [0, 1, 2, 3, 0]


def test_grid_first_beat_on_a_tick():
    period = 0.5
    beats = np.arange(0.23, 30, period)
    g = Grid(beats, period)
    t, ticks = g.slot_times(1)
    # the original first beat must be exactly on a beat tick
    assert np.min(np.abs(t - 0.23)) < 1e-9
    assert g.pad >= 0.05
    assert abs(g.bpm - 120) < 1e-6


def test_viterbi_prefers_stability():
    # noisy evidence alternating between states 0 and 1 with a weak preference for 0
    E = np.array([[1.0, 0.9], [0.9, 1.0], [1.0, 0.9], [0.9, 1.0]])
    assert viterbi(E, change_cost=0.6) == [0, 0, 0, 0]
    assert viterbi(E, change_cost=0.0) == [0, 1, 0, 1]


def test_fold_octaves_removes_octave_jumps():
    ev = [{"midi": m} for m in (40, 52, 40, 52, 43, 55)]
    fold_octaves(ev)
    assert len({e["midi"] % 12 for e in ev}) == 2
    assert max(e["midi"] for e in ev) - min(e["midi"] for e in ev) <= 7


def _events(midis, step=RES // 2):
    return [{"tick": i * step, "t": i * 0.25, "midi": m, "width": 1} for i, m in enumerate(midis)]


def test_lanes_follow_pitch_order_and_repeat():
    riff = [40, 43, 45, 43] * 8  # same riff, 8 times
    ev = arrange.assign_lanes(_events(riff))
    lanes = [e["lane"] for e in ev]
    assert lanes[:4] == lanes[4:8] == lanes[-4:]           # repeats look the same
    assert lanes[0] < lanes[1] < lanes[2]                   # higher pitch = further right
    assert all(0 <= x <= 4 for x in lanes)


def test_lanes_leave_room_for_chords():
    ev = _events([40, 47, 52, 55, 59, 62])
    ev[0]["width"] = 2
    arrange.assign_lanes(ev)
    assert max(e["lane"] for e in ev) <= 3


def _full_events(n=64):
    out = []
    for i in range(n):
        tick = i * RES // 2
        out.append({"tick": tick, "t": i * 0.17, "mc": metric_class(tick), "midi": 40 + (i // 8) % 3 * 2,
                    "accent": i % 8 == 0, "strength": 1.0, "sus_t": 0.0, "width": 2 if i % 8 == 0 else 1,
                    "next_t": (i + 1) * 0.17, "next_tick": tick + RES // 2, "lane": (i // 8) % 3})
    return out


@pytest.mark.parametrize("level", ["Expert", "Hard", "Medium", "Easy"])
def test_difficulty_density_and_gaps(level):
    ev = _full_events()
    notes = arrange.reduce(ev, level, DEFAULT)
    cfg = DEFAULT.difficulties[level]
    ticks = [t for t, _, _ in notes]
    assert ticks == sorted(ticks)
    assert min(np.diff(ticks)) >= min(cfg["gap_k_imp"], cfg["gap_k"])
    assert all(len(l) <= cfg["width"] and max(l) < 5 for _, l, _ in notes)
    if level == "Easy":
        assert all(max(l) < 3 for _, l, _ in notes)


def test_difficulties_get_sparser():
    ev = _full_events()
    n = [len(arrange.reduce(ev, lvl, DEFAULT)) for lvl in ("Expert", "Hard", "Medium", "Easy")]
    assert n == sorted(n, reverse=True) and n[0] > n[-1]


def test_chart_roundtrip_and_sng(tmp_path):
    diffs = {d: [(RES, [0], 0), (2 * RES, [1, 2], RES), (4 * RES, [4], 0)] for d in chart.DIFF_ORDER}
    folder = tmp_path / "song"
    folder.mkdir()
    chart.write_chart(str(folder / "notes.chart"), "T", "A", "me", ["0 = TS 4", "0 = B 120000"], diffs)
    chart.write_ini(str(folder / "song.ini"), title="T", artist="A", album="", year="", genre="Rock",
                    charter="me", length_ms=10000)
    (folder / "song.ogg").write_bytes(os.urandom(1000))
    c = chartio.load(str(folder))
    ex = c["diffs"]["Expert"]
    assert [round(x[0], 6) for x in ex] == [0.5, 1.0, 2.0]       # 120 BPM: beat = 0.5 s
    assert ex[1][1] == [1, 2] and abs(ex[1][2] - 0.5) < 1e-9     # chord + one-beat sustain

    dst = tmp_path / "song.sng"
    sng.pack_folder(str(folder), str(dst))
    meta, files, names = sng.read_sng(str(dst))
    assert meta["name"] == "T" and meta["diff_guitar"] == "3"
    for n in names:
        assert files[n] == (folder / n).read_bytes()
    first = dst.read_bytes()
    sng.pack_folder(str(folder), str(dst))
    assert dst.read_bytes() == first                               # packing is deterministic


def test_smear_before_real_attack_is_dropped():
    from autochart.onsets import _drop_smears
    from autochart.params import DEFAULT, RES
    ev = lambda tick, flux, ab, mc: {"tick": tick, "flux": flux, "abs": ab, "mc": mc}  # noqa: E731
    events = [ev(0, False, 0.3, 1), ev(RES // 4, True, 0.9, 3), ev(RES, False, 0.3, 1), ev(RES + RES // 2, True, 0.9, 2)]
    out = _drop_smears(events, DEFAULT)
    assert [e["tick"] for e in out] == [RES // 4, RES, RES + RES // 2]

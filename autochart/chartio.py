"""Read Clone Hero / YARG charts (.chart or notes.mid) into a common structure.

load(folder_or_file) -> {"tempo": [(tick, bpm)], "res": int, "offset": s,
                         "diffs": {"Expert": [(t_sec, [frets], sustain_sec, tick)], ...},
                         "beats": np.array of beat times (seconds)}
Frets 0..4 = green..orange, 7 = open (reported as -1).
"""
import os
import re

import numpy as np

DIFFS = ["Expert", "Hard", "Medium", "Easy"]


class TempoMap:
    def __init__(self, res, tempos, offset=0.0):
        self.res = res
        self.tempos = sorted(tempos)  # (tick, bpm)
        if not self.tempos or self.tempos[0][0] != 0:
            self.tempos.insert(0, (0, 120.0))
        self.seg = []
        t, last_tick, spt = 0.0, 0, 60.0 / self.tempos[0][1] / res
        for tick, bpm in self.tempos:
            t += (tick - last_tick) * spt
            last_tick, spt = tick, 60.0 / bpm / res
            self.seg.append((tick, t, spt))
        self.ticks = np.array([s[0] for s in self.seg])
        self.offset = offset

    def sec(self, tick):
        i = max(0, int(np.searchsorted(self.ticks, tick, side="right")) - 1)
        s = self.seg[i]
        return s[1] + (tick - s[0]) * s[2] + self.offset

    def beat_times(self, end_tick):
        return np.array([self.sec(k) for k in range(0, int(end_tick) + 1, self.res)])


def _from_chart(path):
    txt = open(path, encoding="utf-8-sig", errors="replace").read()
    blocks = dict(re.findall(r"\[(\w+)\]\s*\{(.*?)\}", txt, flags=re.S))
    res = int(re.search(r"Resolution\s*=\s*(\d+)", blocks.get("Song", "")).group(1))
    m = re.search(r"Offset\s*=\s*([-\d.]+)", blocks.get("Song", ""))
    offset = float(m.group(1)) if m else 0.0
    tempos = [(int(t), int(v) / 1000) for t, v in re.findall(r"(\d+)\s*=\s*B\s+(\d+)", blocks["SyncTrack"])]
    tm = TempoMap(res, tempos, offset)
    diffs, last = {}, 0
    for d in DIFFS:
        notes = {}
        for tick, fret, sus in re.findall(r"(\d+)\s*=\s*N\s+(\d+)\s+(\d+)", blocks.get(f"{d}Single", "")):
            tick, f, sus = int(tick), int(fret), int(sus)
            if f <= 4 or f == 7:
                e = notes.setdefault(tick, [[], 0])
                e[0].append(f if f <= 4 else -1)
                e[1] = max(e[1], sus)
                last = max(last, tick + sus)
        diffs[d] = [(tm.sec(t), sorted(v[0]), (tm.sec(t + v[1]) - tm.sec(t)) if v[1] else 0.0, t)
                    for t, v in sorted(notes.items())]
    return {"res": res, "tempo": tm.tempos, "tm": tm, "diffs": diffs, "beats": tm.beat_times(last)}


def _from_mid(path):
    import mido
    mid = mido.MidiFile(path, clip=True)  # clip: Phase Shift sysex events carry bytes > 127
    res = mid.ticks_per_beat
    tempos = []
    tick = 0
    for msg in mid.tracks[0]:
        tick += msg.time
        if msg.type == "set_tempo":
            tempos.append((tick, mido.tempo2bpm(msg.tempo)))
    tm = TempoMap(res, tempos)
    guitar = None
    for tr in mid.tracks:
        if tr.name.strip().upper() in ("PART GUITAR", "T1 GEMS"):
            guitar = tr
            break
    base = {"Expert": 96, "Hard": 84, "Medium": 72, "Easy": 60}
    diffs = {d: {} for d in DIFFS}
    if guitar is None:
        return {"res": res, "tempo": tm.tempos, "tm": tm, "diffs": {d: [] for d in DIFFS}, "beats": np.array([])}
    tick, on, last = 0, {}, 0
    for msg in guitar:
        tick += msg.time
        if msg.type not in ("note_on", "note_off"):
            continue
        for d, b in base.items():
            if b <= msg.note <= b + 4:
                fret = msg.note - b
                if msg.type == "note_on" and msg.velocity > 0:
                    on[(d, fret)] = tick
                else:
                    st = on.pop((d, fret), None)
                    if st is not None:
                        e = diffs[d].setdefault(st, [[], 0])
                        e[0].append(fret)
                        length = tick - st
                        e[1] = max(e[1], length if length > res // 3 else 0)  # MIDI notes always have length
                        last = max(last, tick)
    out = {}
    for d in DIFFS:
        out[d] = [(tm.sec(t), sorted(v[0]), (tm.sec(t + v[1]) - tm.sec(t)) if v[1] else 0.0, t)
                  for t, v in sorted(diffs[d].items())]
    return {"res": res, "tempo": tm.tempos, "tm": tm, "diffs": out, "beats": tm.beat_times(last)}


def load(path):
    if os.path.isdir(path):
        for n in ("notes.chart", "notes.mid"):
            p = os.path.join(path, n)
            if os.path.exists(p):
                path = p
                break
    return _from_mid(path) if path.endswith(".mid") else _from_chart(path)

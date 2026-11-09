"""Command line: `autochart generate | evaluate | view | pack`."""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__


def _generate(a):
    from .pipeline import generate
    for path in a.audio:
        title = a.title or os.path.splitext(os.path.basename(path))[0]
        r = generate(path, a.artist, title, a.out, cache_dir=a.cache, album=a.album, year=a.year, genre=a.genre,
                     charter=a.charter, fmt=a.format, render=not a.no_audio)
        n = r.meta["notes"]
        print(f"{r.path}\n  {r.meta['bpm']:.2f} BPM ({r.meta['mode']}), notes E/H/M/E "
              f"{n['Expert']}/{n['Hard']}/{n['Medium']}/{n['Easy']}")


def _evaluate(a):
    from .evaluate import evaluate
    rows = []
    for ref in a.reference:
        r = evaluate(ref, a.cache)
        rows.append(r)
        print(f"\n{r['song']}  {r['bpm']} BPM ({r['tempo_mode']})")
        for d in ("Expert", "Hard", "Medium", "Easy"):
            s = r[d]
            print(f"  {d:6s} F1 {s['f1']:.2f} (P {s['precision']:.2f} R {s['recall']:.2f})  notes {s['n_gen']}/{s['n_ref']}"
                  f"  contour {s['contour_bal']:.2f}  chords {s['chords_gen']:.2f}/{s['chords_ref']:.2f}"
                  f"  sustains {s['sustain_gen']:.2f}/{s['sustain_ref']:.2f}", flush=True)
    if len(rows) > 1:
        print("\nMEAN")
        for d in ("Expert", "Hard", "Medium", "Easy"):
            f1 = sum(r[d]["f1"] for r in rows) / len(rows)
            cb = sum(r[d]["contour_bal"] for r in rows) / len(rows)
            print(f"  {d:6s} F1 {f1:.3f}  contour {cb:.3f}")
    if a.json:
        with open(a.json, "w") as f:
            json.dump(rows, f, indent=1)


def _view(a):
    from . import chartio, sng
    import tempfile
    path = a.chart
    if path.endswith(".sng"):
        tmp = tempfile.mkdtemp()
        sng.extract(path, tmp, want={"notes.chart", "notes.mid"})
        path = tmp
    c = chartio.load(path)
    res, tm = c["res"], c["tm"]
    by = {d: {n[3]: n for n in c["diffs"][d]} for d in chartio.DIFFS}
    k = 0
    while tm.sec(k) < a.start:
        k += res // 4
    print("   time   Expert  Hard    Medium  Easy      (GRYBO = frets, ~ = sustain, | = bar)")
    while tm.sec(k) <= a.end:
        cells = []
        for d in chartio.DIFFS:
            n = by[d].get(k)
            cells.append("".join("GRYBO"[f] if f in n[1] else "-" for f in range(5)) + ("~" if n[2] > 0 else " ")
                         if n else ("  .   " if k % res == 0 else "      "))
        if any(c.strip(" .") for c in cells) or k % res == 0:
            mark = "|" if k % (4 * res) == 0 else ("." if k % res == 0 else " ")
            print(f"{tm.sec(k):7.2f}{mark} " + "  ".join(cells))
        k += res // 4


def _pack(a):
    from . import sng
    for folder in a.folders:
        dst = os.path.join(a.out, os.path.basename(os.path.normpath(folder)) + ".sng")
        sng.pack_folder(folder, dst)
        print(dst)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="autochart", description="Automatic guitar charts for YARG / Clone Hero.")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="chart one or more audio files")
    g.add_argument("audio", nargs="+", help="audio file(s): wav, flac, mp3, ogg...")
    g.add_argument("--artist", required=True)
    g.add_argument("--title", help="song title (default: file name; only sensible with one file)")
    g.add_argument("--album", default="")
    g.add_argument("--year", default="")
    g.add_argument("--genre", default="Rock")
    g.add_argument("--charter", default="autochart", help="name shown as charter in the game")
    g.add_argument("--format", choices=["sng", "folder"], default="sng")
    g.add_argument("--out", default=".", help="output directory")
    g.add_argument("--cache", default=os.environ.get("AUTOCHART_CACHE", "cache"), help="stems/transcription cache")
    g.add_argument("--no-audio", action="store_true", help="chart only, skip song.ogg/guitar.ogg")
    g.set_defaults(fn=_generate)

    e = sub.add_parser("evaluate", help="score the generator against human charts (.sng or folders with audio)")
    e.add_argument("reference", nargs="+")
    e.add_argument("--cache", default=os.environ.get("AUTOCHART_CACHE", "cache"))
    e.add_argument("--json", help="write all scores to this file")
    e.set_defaults(fn=_evaluate)

    v = sub.add_parser("view", help="print a chart as text (all four difficulties side by side)")
    v.add_argument("chart", help=".sng file, song folder or notes.chart")
    v.add_argument("start", type=float)
    v.add_argument("end", type=float)
    v.set_defaults(fn=_view)

    pk = sub.add_parser("pack", help="pack song folders into .sng files")
    pk.add_argument("folders", nargs="+")
    pk.add_argument("--out", default=".")
    pk.set_defaults(fn=_pack)

    a = ap.parse_args(argv)
    if a.cmd == "generate" and a.title and len(a.audio) > 1:
        ap.error("--title only works with a single audio file")
    try:
        a.fn(a)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"autochart: error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

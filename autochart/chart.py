"""Writers: notes.chart (Clone Hero / YARG text format) and song.ini."""
from __future__ import annotations

from .params import RES

DIFF_ORDER = ("Expert", "Hard", "Medium", "Easy")


def star_power(track, every_beats: int = 64, length_beats: int = 8) -> list[str]:
    """Placeholder Star Power phrases: 8 beats every 16 bars. (Not musically placed - see LIMITATIONS.)"""
    sp, ticks = [], [t for t, _, _ in track]
    start = every_beats * RES // 2
    while ticks and start < ticks[-1]:
        sp.append(f"{start} = S 2 {length_beats * RES}")
        start += every_beats * RES
    return sp


def write_chart(path: str, title: str, artist: str, charter: str, sync: list[str], diffs: dict) -> None:
    lines = ["[Song]", "{", f'  Name = "{title}"', f'  Artist = "{artist}"', f'  Charter = "{charter}"',
             f"  Resolution = {RES}", "  Offset = 0", '  MusicStream = "song.ogg"', '  GuitarStream = "guitar.ogg"', "}",
             "[SyncTrack]", "{", *("  " + s for s in sync), "}", "[Events]", "{", "}"]
    for name in DIFF_ORDER:
        track = diffs[name]
        ev = [(tick, f"{tick} = N {ln} {sus}") for tick, lanes, sus in track for ln in lanes]
        ev += [(int(s.split(" = ")[0]), s) for s in star_power(track)]
        ev.sort(key=lambda x: x[0])
        lines += [f"[{name}Single]", "{", *("  " + s for _, s in ev), "}"]
    with open(path, "w", encoding="utf-8", newline="\r\n") as f:  # CRLF, like Moonscraper
        f.write("\n".join(lines) + "\n")


def write_ini(path: str, *, title: str, artist: str, album: str, year: str, genre: str, charter: str,
              length_ms: int) -> None:
    # diff_guitar must be >= 0, otherwise YARG treats the guitar part as absent
    with open(path, "w", encoding="utf-8") as f:
        f.write("[song]\n"
                f"name = {title}\nartist = {artist}\nalbum = {album}\nyear = {year}\ngenre = {genre}\n"
                f"charter = {charter}\nsong_length = {length_ms}\npreview_start_time = {length_ms // 3}\n"
                "diff_guitar = 3\ndelay = 0\nloading_phrase = Auto-generated chart.\n")

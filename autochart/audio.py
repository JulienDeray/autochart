"""Audio I/O: source separation (Demucs), transcription (Basic Pitch), rendering (ffmpeg), with a cache.

Everything heavy is cached under `cache_dir`, keyed by a hash of the *content* of the input file, so
renaming a file never reuses the wrong stems and identical files never get separated twice.

Determinism: Demucs applies a random time shift during inference (`shifts=1`). We seed Python, NumPy and
PyTorch before every separation, so the same file always gives the same stems on the same machine and
library versions. Basic Pitch (ONNX) and all later stages are deterministic.
"""
from __future__ import annotations

import hashlib
import os
import random
import shutil
import subprocess
import tempfile

import numpy as np

from .params import STEMS

SEED = 0
BITEXACT = ("-fflags", "+bitexact", "-flags:a", "+bitexact")  # fixed Ogg serial -> reproducible files


def ffmpeg() -> str:
    exe = os.environ.get("FFMPEG") or shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg not found: install it or set FFMPEG=/path/to/ffmpeg")
    return exe


def file_hash(path: str, n: int = 16) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:n]


def separate(audio: str, cache_dir: str, model: str = "htdemucs_6s") -> dict[str, str]:
    """Split `audio` into 6 stems. Returns {stem: wav_path}."""
    out = os.path.join(cache_dir, "stems", f"{model}-{file_hash(audio)}")
    paths = {s: os.path.join(out, s + ".wav") for s in STEMS}
    if all(os.path.exists(p) for p in paths.values()):
        return paths
    import torch
    from demucs.separate import main as demucs_main
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    with tempfile.TemporaryDirectory(dir=cache_dir if os.path.isdir(cache_dir) else None) as tmp:
        demucs_main(["-n", model, "-o", tmp, "--filename", "{stem}.{ext}", audio])
        os.makedirs(os.path.dirname(out), exist_ok=True)
        src = os.path.join(tmp, model)
        tmp_out = out + ".partial"
        shutil.rmtree(tmp_out, ignore_errors=True)
        shutil.move(src, tmp_out)
        os.replace(tmp_out, out)  # atomic: a killed run never leaves half a cache entry
    return paths


def posteriorgrams(wav: str, cache_dir: str):
    """Basic Pitch on a stem -> (note [frames x 88], onset [frames x 88], frame_times). MIDI 21..108."""
    npz = os.path.join(cache_dir, "basic_pitch", file_hash(wav) + ".npz")
    if os.path.exists(npz):
        z = np.load(npz)
        return z["note"].astype(np.float32), z["onset"].astype(np.float32), z["times"]
    from basic_pitch import ICASSP_2022_MODEL_PATH
    from basic_pitch.inference import Model, predict
    from basic_pitch.note_creation import model_frames_to_time
    model = Model(os.path.join(os.path.dirname(str(ICASSP_2022_MODEL_PATH)), "nmp.onnx"))
    raw, _, _ = predict(wav, model)
    note, onset = raw["note"], raw["onset"]
    times = model_frames_to_time(note.shape[0])
    os.makedirs(os.path.dirname(npz), exist_ok=True)
    np.savez_compressed(npz, note=note.astype(np.float16), onset=onset.astype(np.float16), times=times)
    # same float16 round-trip as a cache hit, so first and later runs give identical charts
    return note.astype(np.float16).astype(np.float32), onset.astype(np.float16).astype(np.float32), times


def render(stems: dict[str, str], pad: float, folder: str) -> None:
    """song.ogg = every stem but the guitar, guitar.ogg = guitar stem (the game mutes it on misses).
    Both are delayed by `pad` seconds to line up with the chart's first beat."""
    ff, delay = ffmpeg(), int(round(pad * 1000))
    backing = [stems[s] for s in STEMS if s != "guitar"]
    cmd = [ff, "-y", "-loglevel", "error"]
    for x in backing:
        cmd += ["-i", x]
    cmd += ["-filter_complex", f"amix=inputs={len(backing)}:normalize=0,adelay={delay}:all=1[a]", "-map", "[a]",
            *BITEXACT, "-c:a", "libvorbis", "-q:a", "5", os.path.join(folder, "song.ogg")]
    subprocess.run(cmd, check=True)
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", stems["guitar"], "-af", f"adelay={delay}:all=1", *BITEXACT,
                    "-c:a", "libvorbis", "-q:a", "5", os.path.join(folder, "guitar.ogg")], check=True)

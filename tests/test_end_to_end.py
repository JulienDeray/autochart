"""Slow end-to-end test. Needs the models, ffmpeg and a real song:

    AUTOCHART_TEST_AUDIO=/path/to/song.wav pytest -m slow
"""
import os

import pytest

from autochart import chartio, sng
from autochart.pipeline import generate

AUDIO = os.environ.get("AUTOCHART_TEST_AUDIO")


@pytest.mark.slow
@pytest.mark.skipif(not AUDIO, reason="set AUTOCHART_TEST_AUDIO to a song file")
def test_generate_is_deterministic(tmp_path):
    a = generate(AUDIO, "Test", "Song", str(tmp_path / "a"), cache_dir=str(tmp_path / "cache_a"))
    b = generate(AUDIO, "Test", "Song", str(tmp_path / "b"), cache_dir=str(tmp_path / "cache_b"))
    assert open(a.path, "rb").read() == open(b.path, "rb").read()
    out = tmp_path / "x"
    sng.extract(a.path, str(out))
    c = chartio.load(str(out))
    n = [len(c["diffs"][d]) for d in chartio.DIFFS]
    assert n[0] > 50 and n == sorted(n, reverse=True)

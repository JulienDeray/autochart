# autochart

**Automatic 5-fret guitar charts for [YARG](https://yarg.in) and Clone Hero, from any audio file.**

You have a song nobody has charted. autochart listens to it and writes a playable lead-guitar chart
with all four difficulties, packed as a `.sng` file you drop into your songs folder.

```bash
autochart generate "Instinct sauvage.flac" --artist "Tagada Jones"
# -> Tagada Jones - Instinct sauvage.sng   (Expert, Hard, Medium, Easy + audio)
```

It is not a human charter (read [the limitations](docs/LIMITATIONS.md)), but on punk, rock and metal
it produces charts that are in time, follow the riffs and get sensibly easier from Expert to Easy.

## How it works, in one paragraph

A neural network ([Demucs](https://github.com/facebookresearch/demucs)) separates the song into guitar,
bass, drums, vocals and the rest. The **drums** give the beat grid: a constant tempo for click-track
recordings, a tempo-following grid otherwise. The **guitar** gives the rhythm: an attack detector and
Spotify's [Basic Pitch](https://github.com/spotify/basic-pitch) transcription model vote on every 16th
note. **Basic Pitch plus the bass line** give each note its chord root, smoothed so a repeated chord
stays one chord. Roots become frets with an optimiser that keeps pitch order locally and the same chord
on the same fret song-wide, so riffs look the same each time they come back. Sustains come from how long
the guitar rings. Easier difficulties keep the musically important notes (downbeats, accents, chord
changes) at the densities official charts use.

The full story, with what each stage fixes and why: **[docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md)**.

## Install

Python 3.10–3.12 and [ffmpeg](https://ffmpeg.org) on your `PATH` (or `FFMPEG=/path/to/ffmpeg`).

```bash
git clone <this repo> autochart && cd autochart
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt                         # exact tested versions (CPU)
pip install --no-deps basic-pitch==0.4.0                # see note below
pip install --no-deps -e .
autochart --version
```

`basic-pitch` must be installed with `--no-deps`: its package metadata requires TensorFlow, which
autochart doesn't need (it runs the ONNX model bundled with basic-pitch through `onnxruntime`).

`requirements.txt` pins the versions the benchmarks were run with (`torch 2.2.2`, the last release with
Intel-Mac wheels). On Linux / Windows / Apple Silicon, newer `torch` works too; `pyproject.toml` lists the
compatible ranges. A GPU is not needed. First run downloads the Demucs model (~55 MB).

## Use

```bash
# one song, explicit title
autochart generate song.wav --artist "Band" --title "Song" --album "Album" --year 2024 --genre Punk

# several songs at once (titles from file names), into a folder
autochart generate *.flac --artist "Band" --out charts/

# a song folder (notes.chart, song.ini, song.ogg, guitar.ogg) instead of .sng, to edit in Moonscraper
autochart generate song.wav --artist "Band" --format folder

# look at a chart as text: seconds 40 to 55, all four difficulties side by side
autochart view "charts/Band - Song.sng" 40 55

# score the generator against charts you trust (needs their audio)
autochart evaluate reference/*.sng --json scores.json

# pack edited song folders back into .sng
autochart pack "Band - Song/" --out charts/
```

Then copy the `.sng` into YARG's (or Clone Hero's) songs folder and rescan.

Expect about two minutes per three-minute song on a laptop CPU, most of it in source separation. Stems
and transcriptions are cached (`--cache`, default `./cache`), so re-running is quick.

**Use a good source.** A lossless or high-bitrate studio master gives the cleanest separation. Live
recordings, crowd noise and heavy mastering all cost accuracy.

## Output

| file | |
|---|---|
| `notes.chart` | Expert/Hard/Medium/Easy lead guitar, tempo map, placeholder Star Power |
| `song.ini` | metadata; `charter` = `--charter` + autochart version |
| `song.ogg` | everything except the guitar |
| `guitar.ogg` | the separated guitar (the game mutes it when you miss) |

Same input file + same library versions → byte-identical output.

## How good is it?

Against seven official / hand-made charts (punk, hard rock, metal), the generated Expert notes match
the human charter's within ±70 ms with F1 0.76; Medium 0.60, Easy
0.46. Details, method and how to reproduce: [docs/EVALUATION.md](docs/EVALUATION.md).
The first playtester's verdict: "much better", Medium "accessible", Hard "hard but fair".

## Limitations

One guitar part (rhythm and lead are merged), approximate fret movement, 4/4 only, Star Power not
musically placed, tuned on distorted rock. All of it, with symptoms and causes:
**[docs/LIMITATIONS.md](docs/LIMITATIONS.md)**.

## Project layout

```
autochart/        the package: audio, beatgrid, grid, onsets, pitch, arrange, chart, sng, chartio,
                  pipeline, evaluate, cli, params (all tunable constants, documented)
tests/            unit tests (fast, no models) + an optional end-to-end determinism test
docs/             HOW_IT_WORKS, EVALUATION, LIMITATIONS
```

```bash
pip install pytest && pytest                                   # fast tests
AUTOCHART_TEST_AUDIO=song.wav pytest -m slow                    # end to end, ~5 min
```

## Contributing

Changes to the analysis should come with `autochart evaluate` numbers before and after, on more than one
song. Improvements that would matter most: separating rhythm from lead guitar, musical Star Power and
sections, time signatures other than 4/4, and more benchmark charts outside rock.

## Credits and licence

MIT licence (see `LICENSE`). Built on [Demucs](https://github.com/facebookresearch/demucs) (MIT, Meta),
[Basic Pitch](https://github.com/spotify/basic-pitch) (Apache 2.0, Spotify),
[librosa](https://librosa.org) (ISC). The `.sng` container format is the one used by
[Chorus Encore](https://www.enchor.us), YARG and Clone Hero.

Charts you generate are derived from the recording you gave it; sharing them follows the same copyright
considerations as any fan chart. This repository contains no music and no third-party charts.

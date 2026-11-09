# How autochart works

A guitar chart is three decisions per note: **when** (rhythm), **which fret** (lanes, chords) and **how
long** (sustains), repeated for four difficulties. A human charter makes them by ear. autochart makes
them from measurements, and each stage below exists because a simpler version failed in a measurable way.

```
audio ──► Demucs ──► drums ──► beat grid ─────────────┐
            │                                         ▼
            ├──► guitar ──► spectral flux ──► onsets per 16th slot ──► big-stab cleanup
            │       └─────► Basic Pitch ───┬──► (onset probabilities)            │
            │                              └──► note probabilities ──► chord root ◄── bass vote
            └──► bass ────► Basic Pitch ───────────────────────────────────┘     │
                                                                                  ▼
                       octave folding ─► sustains & chord shapes ─► lanes ─► 4 difficulties ─► .sng
```

Code map: `audio.py` (separation, transcription, rendering) · `beatgrid.py` · `grid.py` · `onsets.py` ·
`pitch.py` · `arrange.py` (shapes, lanes, difficulties) · `chart.py` / `sng.py` (output) ·
`pipeline.py` (glue) · `evaluate.py` (benchmarks) · `params.py` (every tunable constant).

---

## 1. Source separation: get the guitar alone

[Demucs](https://github.com/facebookresearch/demucs) `htdemucs_6s` splits the mix into guitar, bass,
drums, vocals, piano and "other". Everything downstream listens to the stem that matters: the drums for
the tempo, the guitar for notes, the bass to confirm chord roots.

The guitar stem doubles as the game's `guitar.ogg` (YARG mutes it when you miss); the five other stems
are mixed into `song.ogg`.

Separation is imperfect: rhythm and lead guitars land in the same stem, keyboards and bass can bleed
in. That is the first source of error and a hard ceiling for everything after it.

## 2. Beat grid: where the beats are

Everything in a chart sits on a grid of beats, so the grid has to be right first. This was the biggest
flaw of the first version: a standard beat tracker (librosa) estimated the tempo beat by beat and
wandered between 148 and 246 BPM on a song recorded to a 180.0 BPM click. Notes drifted up to 350 ms
off the music, and nothing downstream could fix that.

Now two candidate grids are built from the drum stem's onset envelope:

- **Constant tempo.** An exhaustive search over tempo (±3 % around a first estimate, 241 steps) and
  phase (4 ms steps), scoring how much drum energy falls on beats, 8ths and 16ths, then refined. Songs
  recorded to a click get a perfect, drift-free grid.
- **Tempo-following.** For bands recording without a click: dynamic-programming beat tracking with a
  slowly varying tempo, each beat snapped to the nearest strong drum hit, then smoothed. Smoothing works
  on the beat *times*, never on the periods: integrating smoothed periods accumulates drift.

The winner is the grid that puts more drum hits within 30 ms of its 8th notes; the tempo-following
grid must win by 10 points (live-played songs win by 15–45, click songs by 0–5). Then the whole grid moves 20 ms earlier, because onset detectors peak a frame
or two after the attack you hear (+14 to +26 ms against four hand-made tempo maps).

Finally the audio gets a short silence (`pad`) so that the first beat falls exactly on a chart tick. The
chart is written at 192 ticks per beat with one tempo (click songs) or one tempo marker per beat.

## 3. Onsets: when the guitar plays

Every 16th-note slot of the grid is a candidate note. Two detectors vote:

- **Spectral flux** of the guitar stem: how much the spectrum changes, the classic attack detector. It
  is normalised against its own ±2-bar neighbourhood, so a quiet verse and a wall-of-sound chorus are
  judged alike.
- **Basic Pitch** ([Spotify](https://github.com/spotify/basic-pitch)), a small neural transcription
  model, gives the probability that a note *starts* at each moment for each pitch. It hears chord changes
  and legato notes that have no loud attack. Adding it lifted onset accuracy (F1 against human charts)
  from 0.62 to 0.75.

Either detector can trigger a note, with thresholds that depend on where the slot falls: a downbeat
needs little evidence, an isolated 16th needs a lot and must be a local peak. Below 100 BPM a 16th lasts
as long as an 8th at 180 BPM and is judged like one.

### The "boom" problem

Players feel the big accented chords of a riff more than anything else. Playtesting showed they were
the weak spot: when a distorted chord rings, Basic Pitch keeps reporting note starts across the whole
ring. The real hit drowned in a dozen filler notes, especially the first time a pattern appeared.

So an attack much louder than the song's usual (1.5 × its 95th-percentile flux) counts as a **stab**.
Between the previous and the next strong attack, weaker notes are removed, but only where the guitar is
ringing. Ringing versus picking is measured as the ratio of flux on beats/8ths to flux on the 16ths in
between: picked 8th-note chugs show a strong pulse, held chords don't. Without that guard, the cleanup
also deleted real chugs and cost 0.14 F1 on one benchmark song. Stabs are always charted as chords.

For every remaining note the guitar stem's level is followed until it drops 9 dB below the attack (how
long it rings), and notes clearly louder than their neighbours are marked as accents.

## 4. Pitch: which chord

A guitar game doesn't show pitch, only movement, but the movement has to come from somewhere.

For each note, Basic Pitch's per-pitch note probabilities are averaged over the first ~200 ms. Rock
guitar is mostly power chords (root + fifth + octave), and a naive "loudest pitch" picks the fifth or
the octave about as often as the root. So each candidate root is scored with a template:

```
root + 0.8·fifth + 0.4·octave − 0.5·(this pitch is the fifth of a lower root) − 0.3·(lower octave)
     + 0.5·(the bass stem plays this pitch class)
```

The bass usually doubles the root and its separated stem is much cleaner than a distorted guitar, so it
gets a vote.

Scores are compared across the whole song, not per note, so a note with weak evidence stays uncertain
instead of confidently following noise. A **Viterbi** pass then chooses the most likely *sequence* of
roots, with a cost for each change. A chord played eight times stays one chord instead of flickering
between D and A, the main reason the first version's lanes "made no sense".

Last, **octave folding**: distorted power chords are often heard an octave off. Each root keeps its
note name but moves to the octave nearest the recent roots, so octave errors don't become lane jumps.

A note is a power chord when its fifth is at least 0.6 × as strong as its root.

## 5. Shapes and sustains

- **Sustain** if the next note is at least ¾ beat away and the guitar still rings after 0.6 beat. With
  the human rhythm given, this rule reproduces official sustains with F1 0.85–1.0.
- **Chords:** power chord → 2 frets. Accented chords or stabs that ring ~2 beats → 3 frets.

## 6. Lanes: from pitch to frets

Five frets for a whole fretboard means the mapping has to be relative. Two goals pull against each other:

1. **Local order:** a higher chord appears further right than the one before it.
2. **Consistency:** the same chord sits on the same fret every time, so a riff *looks* the same when it
   comes back. That's what makes a chart learnable.

Each root gets a *preferred* lane from its position in the song's range (5th–95th percentile spread
over the frets). The song is cut into 2-bar blocks; in each block the distinct roots get strictly
increasing lanes that minimise `Σ count × |lane − preferred lane|`, with a small bonus for showing big
intervals as visible jumps. That is an exact search, at most C(5,4) = 5 options. Identical blocks
always get identical lanes, and a chord only moves when the local order forces it. One lane is kept
free when the song has chords, so 2-note chords fit.

## 7. Difficulties

Human Hard / Medium / Easy charts are *simplifications*, not decimations. Counting notes in official
Harmonix / Neversoft charts shows, at any tempo, roughly: Hard ≈ 8th notes, Medium ≈ one note per beat,
Easy ≈ one note every two beats.

So the Expert notes are ranked by musical importance: downbeat > beat > 8th > 16th, then accents, pitch
changes and held notes. They are kept greedily as long as they respect a minimum gap from notes already
kept, in ticks and in seconds. Important notes may use a tighter gap. Also:

- **Hard:** 5 lanes, up to 2-note chords, unaccented off-beats of fast same-chord chugs dropped.
- **Medium:** 4 lanes, chords only with a beat of space around them (no chord flicker inside a chug).
- **Easy:** 3 lanes, single notes.

Lanes are recomputed for 4 and 3 frets with the same method as Expert, so the movement stays consistent.

## 8. Output

`notes.chart` (text format of Moonscraper / Clone Hero, CRLF), `song.ini` (`diff_guitar` must be ≥ 0 or
YARG ignores the part), `song.ogg`, `guitar.ogg`, packed into one `.sng` file. `.sng` is the container
used by Chorus Encore; YARG and Clone Hero read it directly. Its XOR mask is derived from the content,
so the same input gives a byte-identical file.

## Determinism

Same audio file + same library versions + same machine type → same `.sng`, byte for byte. Demucs's
random time shift is seeded; everything else has no randomness. Different CPUs or library versions can
change floating-point results slightly, which can occasionally flip a borderline note.

## How the numbers were chosen

Every constant in `params.py` was tuned against human charts with `autochart evaluate`, one stage at a
time: the beat grid against hand tempo maps, the onsets against human note times, the pitch stage
against human fret *movement* with the human rhythm given, the sustains likewise. Then the whole
pipeline was checked end to end, and finally playtested. See [EVALUATION.md](EVALUATION.md).

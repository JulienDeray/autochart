# Evaluation

## Method

`autochart evaluate REFERENCE.sng ...` takes charts made by humans, mixes their audio stems back into
a single track, runs the generator on that mix as if it were an unknown song, and compares the result
with the human chart, difficulty by difficulty. Measures:

| metric | meaning |
|---|---|
| **F1** | a generated note matches a human note within ±70 ms. Precision = share of our notes the human also charted; recall = share of the human's notes we found. |
| **contour** | on consecutive matched pairs: when the human moves up/down the frets, do we move the same way; when the human stays, do we stay. `contour` = mean of the two rates. Raw fret equality is meaningless, since charters pick different hand positions. |
| chords, sustains | share of notes that are chords / sustained, ours vs theirs |

Charters disagree with each other too, so 1.0 is not the ceiling of a "perfect" chart. Two careful
human charts of the same song typically differ on chord shapes, sustains and how many ghost notes to
include.

Because the reference charts and their audio are copyrighted, **none are included in this repository**.
Use charts you own; official exports (Harmonix, Neversoft) are best because they ship with separate
audio stems and are consistently charted.

## Benchmark used during development

Seven songs, 90–200 BPM, punk / hard rock / metal: Pennywise *Bro Hymn* (fan chart), The Runaways
*Cherry Bomb*, AC/DC *Let There Be Rock*, Puddle of Mudd *She Hates Me*, Mötley Crüe *Kickstart My
Heart*, Disturbed *Down with the Sickness* (Harmonix), Rammstein *Du Hast* (Neversoft). Four were
recorded without a click track, three with one.

Mean over the seven songs:

| | v0 (first prototype) | v1.1 (this release) |
|---|---|---|
| Expert F1 | 0.74 | 0.76 |
| Hard F1 | 0.70 | 0.71 |
| Medium F1 | 0.44 | 0.60 |
| Easy F1 | 0.29 | 0.46 |
| Expert contour | 0.48 | 0.55 |

Per song (v1.1):

| song | BPM (grid) | Expert | Hard | Medium | Easy | contour |
|---|---|---|---|---|---|---|
| Pennywise - Bro Hymn (ThundahK) | 198 (variable) | 0.78 | 0.73 | 0.70 | 0.42 | 0.61 |
| The Runaways (WaveGroup) - Cherry Bomb (Harmonix) | 137 (variable) | 0.71 | 0.65 | 0.60 | 0.43 | 0.53 |
| ACDC - Let There Be Rock (Harmonix) | 181 (variable) | 0.76 | 0.63 | 0.52 | 0.30 | 0.51 |
| Puddle of Mudd - She Hates Me (Harmonix) | 110 (variable) | 0.88 | 0.84 | 0.68 | 0.57 | 0.55 |
| Mötley Crüe - Kickstart My Heart (Harmonix) | 179 (constant) | 0.70 | 0.58 | 0.52 | 0.35 | 0.49 |
| Rammstein - Du Hast (Neversoft) | 125 (constant) | 0.77 | 0.81 | 0.58 | 0.58 | 0.60 |
| Disturbed - Down with the Sickness (Harmonix) | 90 (constant) | 0.74 | 0.71 | 0.61 | 0.58 | 0.60 |

What the numbers don't show: v0's tempo bug (a wandering beat tracker) didn't affect most benchmark
songs, but it ruined the song that started the project. v1 fixed it, and playtesting there ("much
better", Medium "accessible", Hard "hard but fair") was the real acceptance test. v1.1 then fixed the
remaining playtest complaint (big riff chords drowned in filler notes) without changing benchmark scores.

## Tuning stage by stage

Tuning everything end to end mixes up errors, so each stage was tuned in isolation first:

- **Beat grid** against the human tempo maps: share of human beats within 25/50 ms of our grid. The
  +20 ms latency correction comes from here (measured +14..+26 ms on four songs).
- **Onsets** against human note times (F1 only, pitch ignored). Adding Basic Pitch onsets: 0.62 → 0.75.
- **Pitch and lanes** with the *human* rhythm given ("oracle rhythm"), comparing only movement. Bass vote,
  octave folding and the lane optimiser each added a few points; one-shot "loudest pitch" was near chance.
- **Sustains** with the human rhythm given: the gap + ring rule scores F1 0.85–1.0.
- **Difficulties** by counting notes per beat and per metric position in official charts.

## Reproducing

```bash
autochart evaluate path/to/*.sng --json scores.json
```

The first run separates every song (~1.5 min each on CPU); later runs reuse the cache.

# Limitations

autochart produces a playable, musically sensible first chart. It does not replace a good human
charter. Known limits, roughly by how much a player will notice them:

## What it gets wrong

- **One guitar part.** Demucs puts every guitar in one stem, so rhythm and lead guitars, or two guitars
  playing different things, blend into one part. Solos over a rhythm guitar come out as a mix of both.
- **Pitch movement is approximate.** On the benchmark (Expert, notes matched with the human chart),
  when the human moves up or down the generated chart moves the same way 40 % of the time, and when the
  human stays on the same fret it stays 71 % of the time. Lanes are consistent and follow the chord changes, but a human hears melodies and
  hand positions that the model doesn't.
- **Held versus strummed chords.** A ringing distorted chord and a fast tremolo-picked one look alike in
  the audio. The big-stab cleanup handles the common case (massive accented chords); other held chords
  can still get filler notes, and some fast picking can get under-charted.
- **Chords are a guess.** Power chords are detected well (they dominate rock); full open chords,
  arpeggios and single-note riffs played with octaves can be charted with the wrong shape. Whether a
  passage *should* be single notes or chords is partly charter taste: official charts of the same style
  disagree.
- **Genres.** Tuned and tested on punk, hard rock and metal (90–200 BPM, distorted guitars). Clean
  guitar, acoustic, prog with odd meters or heavy orchestration will be worse.
- **Time signature.** Always 4/4. Songs in 3/4, 6/8 or with meter changes get a misplaced bar structure
  (notes stay in time, but downbeat priorities and bar lines are wrong).
- **Tempo.** Click-track songs are handled very well. Strong rubato, ritardandos, free intros and
  tempo changes mid-song are followed only approximately.
- **Not charted:** Star Power is placed mechanically (8 beats every 16 bars), not on musical phrases.
  No sections/practice markers, no HOPOs/taps beyond what the game derives itself, no open notes, no
  other instruments (bass, drums, vocals), no lyrics.

## What it costs

- **CPU time.** Mostly Demucs: about 1.5 minutes for a 3-minute song on a 2019 laptop CPU, then ~30 s
  for the rest. Everything is cached, so re-running on the same song is fast.
- **Disk.** ~200 MB of stems per song in the cache.

## Reproducibility

Byte-identical output for the same file and library versions on the same machine type. Different CPUs,
operating systems or library versions can change floating-point results slightly; that rarely flips
more than a handful of borderline notes. The tested versions are pinned in `requirements.txt`.

## Legal

autochart only processes audio you give it. Generated charts and the audio inside them are derived from
that recording; sharing them is subject to the copyright of the music, as for any fan chart. The
repository contains no audio and no third-party charts.

## How to judge a chart

`autochart view song.sng 40 55` prints all four difficulties of a time range as text. Common symptoms
and their causes:

| Symptom | Likely cause |
|---|---|
| everything consistently early/late | beat grid: check `bpm` and `mode` (folder output, `autochart.json`) |
| notes on beats where the guitar rests | separation bleed (keys or bass in the guitar stem) |
| lane jumps on a repeated chord | pitch ambiguity (often bass and guitar disagree) |
| big chord buried in small notes | held chord not loud enough to count as a stab |

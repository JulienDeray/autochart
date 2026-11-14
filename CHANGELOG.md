# Changelog

## 1.4.0
- `--taps`: chart a song your way from an Alfred Tapper recording (`tools/tapper.html`, new `guide` module).
  Riffs you played are kept as played. Big held chords are re-read from the audio over the whole hold
  (bass + guitar power-chord root), start where the chord really changes, and keep one chord-to-lane map
  for the whole song. Playtested on Tagada Jones, Instinct sauvage: "really good".
- `--muted-singles`: palm-muted chugs become single notes on Expert and on-the-beat notes on lower levels.
  Off by default, because official charts chord them (chord accuracy -0.06 to -0.14 on the benchmark).
- Default charts are unchanged.

## 1.3.0
- No stray notes after the song ends: notes stop 0.3 s after the guitar's last sustained activity
  (1 s-smoothed level above -30 dB). Found by playtesting the end of Instinct sauvage (Tagada Jones).

## 1.2.0
- No more double hit on syncopated big chords: when Basic Pitch reports a note on the beat and the guitar's
  real attack lands one 16th later (and is clearly louder), only the attack is kept. Found by playtesting
  the first chord of a riff that lands just after the beat. Benchmark mean onset F1 moves by -0.006
  (official charters often quantize such hits onto the beat); kept because it matches the recording.

## 1.1.0
First public release.

- Big-stab cleanup: massive accented chords ("boom" hits) are no longer buried in filler notes while
  they ring; stabs are always charted as chords.
- Deterministic output: seeded source separation, content-derived `.sng` mask, bit-exact Ogg encoding.
- Tempo mode choice made robust (a click-track song could flip to tempo-following mode on tiny
  separation differences).
- Clean package, CLI (`generate`, `evaluate`, `view`, `pack`), content-hashed cache, documentation.

## 1.0 (private)
- Beat grid from the drum stem (constant or tempo-following) with a 20 ms latency correction.
- Basic Pitch onsets and note posteriorgrams, power-chord root template, bass vote, Viterbi smoothing,
  octave folding.
- Lane optimiser (local pitch order + song-wide consistency).
- Sustains from ring time; difficulty reduction calibrated on official charts.

## 0.x (private prototype)
Per-beat tracker, CQT pitch guess, grid decimation for easier levels. Rejected after playtesting:
"rhythm not really there, notes don't make much sense".

Alfred Tapper: record how YOU would play a song, then chart it that way (autochart generate --taps).

1. Open tools/tapper.html in Chrome or Edge (works offline, nothing is uploaded).
2. Pick the song's audio file, set your 5 keys (default 1 2 3 4 5 = green..orange), calibrate once by
   tapping on the clicks.
3. "Start pass" (or Space) and play the song the way it should feel. Hold a key = sustain, several keys at
   once = chord. Where you play nothing, the automatic chart is kept.
4. Do 2-3 full passes (a strum counts only if two passes agree), then "Download recording (.json)".
5. autochart generate song.wav --artist A --title T --taps recording.json [--muted-singles]

Use a wired keyboard and wired audio if you can: Bluetooth adds lag (calibration corrects it, less precisely).

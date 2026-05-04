# Disfluency Clips

Pre-recorded splice assets used by `services/analysis/app/tts/disfluency.py`.

Filenames must match the `_ASSET_MAP` keys in `disfluency.py`:

| Type           | Filename            | Notes                                       |
|----------------|---------------------|---------------------------------------------|
| `silence_200`  | `silence_200ms.wav` | Exactly 200 ms of silence.                  |
| `silence_500`  | `silence_500ms.wav` | Exactly 500 ms of silence.                  |
| `silence_1000` | `silence_1000ms.wav`| Exactly 1 s of silence.                     |
| `silence_2000` | `silence_2000ms.wav`| Exactly 2 s of silence.                     |
| `filler_ko`    | `filler_ko.wav`     | Korean filler ("어…", "음…", ~400 ms each). |
| `filler_en`    | `filler_en.wav`     | English filler ("um", "uh", ~300 ms each).  |
| `breath`       | `breath.wav`        | Audible inhale, ~600 ms.                    |

Encode all assets as 24 kHz mono WAV. The splicer normalizes the rate
and channel count regardless, but matching the target keeps the timing
exact.

If an asset is missing at runtime, the splicer falls back to generated
silence of the requested duration — useful for local development before
real recordings are gathered.

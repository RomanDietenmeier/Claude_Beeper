# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

Claude_Beeper is a Python desktop watcher: once per second it screenshots the desktop, looks for any of the reference images in [imgs_to_detect/](imgs_to_detect/), and plays an audio file from [beeps/](beeps/) when one is found — so the user can step away from the keyboard and be notified when Claude Code finishes, is interrupted, or is waiting on input.

No source code, `requirements.txt`, or entry point exists yet. The implementer creates them.

## Detection contract

This is the behavior the script must satisfy. The numbering matters; later rules amend earlier ones.

1. **Polling cadence.** One screenshot per second.
2. **Detect phase.** For each screenshot, run template matching against every PNG in [imgs_to_detect/](imgs_to_detect/). A "match" is any template whose best correlation score ≥ the threshold (start at 0.85, see *Implementation notes*).
3. **On match.**
   - Pick **one random** file from [beeps/](beeps/) (treat the directory as a flat pool of interchangeable beeps).
   - Play it **once**, asynchronously — do not block the 1 Hz loop on the audio's full duration.
   - Record the playback start time (for rule 6).
   - Transition to the cooldown phase. Do **not** re-trigger on subsequent matches while still in cooldown.
4. **Cooldown phase.** Keep capturing one screenshot per second. Maintain a counter of *consecutive clean* screenshots (no template matches anywhere). Any match resets the counter to 0. Once the counter reaches **3**, return to the detect phase.
5. **Stop-on-disappear.** During cooldown, the *first* clean screenshot must also **stop** any beep that is still playing. The beep exists to alert the user that the state is on screen — if the state is gone, the alert is over. (This is in addition to incrementing the clean counter.)
6. **10 s hard cutoff.** If a beep is still playing 10 seconds after it started, force-stop it. This caps any long audio file regardless of detection state.
7. **Single-stream invariant.** At any moment, at most one beep is playing. Rules 3, 5, and 6 already enforce this in the state machine; the implementation should also use a single-stream audio primitive (see *Recommended stack*) so overlap is structurally impossible rather than relying on bookkeeping.
8. **All templates are one event class.** The four permission-mode arrow variants exist to make matching robust across color tints, not to trigger different beeps. Do not branch behavior on which template matched.

## Recommended stack

- **`mss`** — screen capture. ~30× faster than `pyautogui`/Pillow, cross-platform via ctypes, negligible CPU at 1 Hz. Use `mss().monitors[0]` to capture the union of all monitors.
- **`opencv-python`** — `cv2.matchTemplate` with `TM_SQDIFF_NORMED` and the alpha channel as `mask`. Templates are RGBA: the surrounding "transparent" pixels are *not* a constant background — on a live screen they're whatever prompt content / scrollback happens to be near the glyph — so they must be excluded from scoring, not zeroed. SQDIFF (a difference metric) was chosen over `TM_CCORR_NORMED` (a non-centered correlation) because the latter scores 1.0 on any flat screen region, producing false positives; SQDIFF only scores 0 when masked pixels actually equal the template.
- **`numpy`** — already an OpenCV dependency; needed to convert mss frames into the array shape OpenCV expects.
- **`python-vlc`** — audio. Delegates decoding to a locally-installed VLC, so it plays anything VLC can play (MP3, OPUS, OGG, WAV, FLAC, …). The pure-pip alternatives don't cover Opus: pygame's bundled SDL2_mixer (Windows wheels) is built `formats=ogg,mp3,mod,mid`, and `pyminiaudio`/`just_playback` only do wav/flac/vorbis/mp3. Reuse one `vlc.Instance("--no-video", "--quiet")` and create a fresh `MediaPlayer` per beep — calling `.stop()` on the player you currently hold (combined with the cooldown gate) keeps the single-stream invariant (rule 7) trivially.

## Asset directories

- [imgs_to_detect/](imgs_to_detect/) — committed PNG templates. Each is **tightly cropped** to the smallest stable region of the UI affordance (icon/glyph only, no surrounding chrome) — this was done deliberately in commit `51e5a54` to make matching reliable. Preserve that property when adding or editing images; extra background will hurt match accuracy. Two semantic categories:
  - **Terminal states** (Claude has stopped) — spark/burst glyph: `Claude donepng.png` (completed), `Claude interrupted.png` (interrupted).
  - **Waiting-for-input states** (idle, prompt box ready) — up-arrow submit glyph in four permission-mode tints: `claude not working.png` (default), `claude not working aks before.png` (ask-before), `claude not working autoedit.png` (auto-edit), `claude not working bypass.png` (bypass-permissions).
- [beeps/](beeps/) — user-supplied audio files, **gitignored** (see [.gitignore](.gitignore)). The script picks one at random per trigger; all files are interchangeable. The directory is checked in via `.gitkeep` but its contents are local-only.

## Implementation notes

- Load templates once at startup. Read with `cv2.IMREAD_UNCHANGED` and split into a grayscale BGR portion + the raw alpha channel as the mask. Don't crop or premultiply — the mask handles transparency at score time.
- Convert the screenshot to grayscale once per tick — ~30 % speedup with negligible accuracy loss for these high-contrast glyphs.
- Threshold ≈ 0.10 with `TM_SQDIFF_NORMED` (semantics inverted vs. correlation: **lower is better**, 0 = perfect, 1 ≈ unrelated). Real matches sit near 0 (often < 0.01); raise toward 0.15 if real matches are missed, lower toward 0.05 if false positives appear.
- Wrap the result in `np.nan_to_num(..., nan=1.0, posinf=1.0, neginf=1.0)` before `.min()` — masked SQDIFF emits NaN/±inf for zero-variance regions, and we want those treated as the *worst* possible score (1.0), not the best.
- The script gates two diagnostic side-effects on the `CLAUDE_BEEPER_DEBUG=1` env var: a per-cycle `print(min sqdiff)` and a `_debug_last_screen.png` written to the project root. Use the saved PNG to verify the icon was actually in the captured frame when tuning.
- Use `mss.MSS()` (not the deprecated `mss.mss()`) as the screen-capture context manager.
- For rules 5 and 6, each cooldown tick should call `player.stop()` if the screenshot is clean, and call `player.stop()` if `player.is_playing()` and `time.monotonic() - beep_started_at >= 10`.
- Use `time.monotonic()` (not `time.time()`) for the 10 s timer — wall-clock jumps shouldn't affect it.

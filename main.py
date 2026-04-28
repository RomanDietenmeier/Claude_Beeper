import os
import random
import time
from pathlib import Path

import cv2
import mss
import numpy as np
import vlc

ROOT = Path(__file__).parent
# TM_SQDIFF_NORMED scoring: lower = better. 0 = perfect, 1 = total mismatch.
THRESHOLD = 0.0001
POLL_S = 1.0
CLEAN_REQUIRED = 3
MAX_BEEP_S = 10.0
AUDIO_EXTS = {".mp3", ".opus", ".ogg", ".wav", ".flac", ".m4a"}
DEBUG = os.environ.get("CLAUDE_BEEPER_DEBUG") == "1"


def _load_template(p: Path):
    # RGBA template → grayscale BGR + alpha mask. The mask tells matchTemplate
    # to score only the opaque pixels (the glyph itself), ignoring whatever
    # the screen happens to render in the surrounding "transparent" area.
    img = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
    bgr, alpha = img[:, :, :3], img[:, :, 3]
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), alpha


TEMPLATES = [_load_template(p) for p in (ROOT / "imgs_to_detect").glob("*.png")]
BEEPS = [p for p in (ROOT / "beeps").iterdir() if p.suffix.lower() in AUDIO_EXTS]
VLC = vlc.Instance("--no-video", "--quiet")


def screen_has_match() -> bool:
    with mss.MSS() as sct:
        screen = cv2.cvtColor(np.array(sct.grab(sct.monitors[0])), cv2.COLOR_BGRA2GRAY)
    # TM_SQDIFF_NORMED with mask: 0 = perfect match, ~1 = unrelated. NaN/inf
    # appears for degenerate (zero-variance under mask) regions — replace with
    # 1.0 so they're treated as the worst possible score, not the best.
    best_score, best_idx, best_xy = 1.0, -1, (0, 0)
    for i, (t, m) in enumerate(TEMPLATES):
        result = np.nan_to_num(
            cv2.matchTemplate(screen, t, cv2.TM_SQDIFF_NORMED, mask=m),
            nan=1.0,
            posinf=1.0,
            neginf=1.0,
        )
        y, x = np.unravel_index(int(result.argmin()), result.shape)
        score = float(result[y, x])
        if score < best_score:
            best_score, best_idx, best_xy = score, i, (int(x), int(y))

    print(
        f"min sqdiff: {best_score:.4f}  template[{best_idx}]  at xy={best_xy}",
        flush=True,
    )
    if DEBUG:
        cv2.imwrite(str(ROOT / "_debug_last_screen.png"), screen)
        if best_idx >= 0:
            th, tw = TEMPLATES[best_idx][0].shape
            x, y = best_xy
            cv2.imwrite(
                str(ROOT / "_debug_best_match_crop.png"), screen[y : y + th, x : x + tw]
            )
    return best_score <= THRESHOLD


def play_random_beep() -> "vlc.MediaPlayer":
    player = VLC.media_player_new()
    player.set_media(VLC.media_new(str(random.choice(BEEPS))))
    player.play()
    return player


def main() -> None:
    if not TEMPLATES:
        raise SystemExit("No templates found in imgs_to_detect/")
    if not BEEPS:
        raise SystemExit("No audio files found in beeps/")

    while True:
        while not screen_has_match():
            time.sleep(POLL_S)

        player = play_random_beep()
        beep_start = time.monotonic()

        clean = 0
        while clean < CLEAN_REQUIRED:
            time.sleep(POLL_S)
            if screen_has_match():
                clean = 0
            else:
                clean += 1
                player.stop()
            if player.is_playing() and time.monotonic() - beep_start >= MAX_BEEP_S:
                player.stop()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass

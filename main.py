import os
import random
import time
from pathlib import Path

import cv2
import mss
import numpy as np
import vlc

ROOT = Path(__file__).parent
# TM_SQDIFF_NORMED on full-colour BGR; lower = better, 0 = pixel-perfect.
THRESHOLD = 0.002
POLL_S = 1.0
CLEAN_REQUIRED = 3
MAX_BEEP_S = 10.0
AUDIO_EXTS = {".mp3", ".opus", ".ogg", ".wav", ".flac", ".m4a"}
DEBUG = os.environ.get("CLAUDE_BEEPER_DEBUG") == "1"


TEMPLATES = [cv2.imread(str(p)) for p in (ROOT / "imgs_to_detect").glob("*.png")]
BEEPS = [p for p in (ROOT / "beeps").iterdir() if p.suffix.lower() in AUDIO_EXTS]
VLC = vlc.Instance("--no-video", "--quiet")


def screen_has_match() -> bool:
    with mss.MSS() as sct:
        screen = cv2.cvtColor(np.array(sct.grab(sct.monitors[0])), cv2.COLOR_BGRA2BGR)
    best_score, best_idx, best_xy = 1.0, -1, (0, 0)
    for i, t in enumerate(TEMPLATES):
        result = cv2.matchTemplate(screen, t, cv2.TM_SQDIFF_NORMED)
        y, x = np.unravel_index(int(result.argmin()), result.shape)
        score = float(result[y, x])
        if score < best_score:
            best_score, best_idx, best_xy = score, i, (int(x), int(y))
    if DEBUG:
        print(
            f"score: {best_score:.4f}  template[{best_idx}]  at xy={best_xy}",
            flush=True,
        )
        cv2.imwrite(str(ROOT / "_debug_last_screen.png"), screen)
        if best_idx >= 0:
            th, tw = TEMPLATES[best_idx].shape[:2]
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

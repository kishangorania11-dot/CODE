#!/usr/bin/env python3
"""Generate a talking-avatar video from a reference photo and a recorded
audio clip, using the free kevinwang676/SadTalker Hugging Face Space.

Usage:
    python scripts/generate_avatar_video.py <photo_path> <audio_path> <output_path>

The photo is a still image of the presenter's face (reused across videos).
The audio is a fresh recording of them reading that day's script - this
step is intentionally manual (see project notes on why we don't clone
voices without live, per-video consent).
"""

import sys
from pathlib import Path

from gradio_client import Client, handle_file

SPACE = "kevinwang676/SadTalker"


def generate(photo_path: str, audio_path: str, output_path: str):
    client = Client(SPACE)

    result = client.predict(
        source_image=handle_file(photo_path),
        input_audio=handle_file(audio_path),
        preprocess="crop",
        still_mode_fewer_hand_motion_works_with_preprocess_full=True,
        gfpgan_as_face_enhancer=True,
        batch_size_in_generation=1,
        face_model_resolution="256",
        pose_style=0,
        api_name="/predict",
    )

    # result is a filepath (or dict with a filepath) to the generated video
    video_path = result if isinstance(result, str) else result.get("video", result)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(video_path).rename(output_path) if Path(video_path).exists() else None
    print(f"Generated video saved to: {output_path}")
    return output_path


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python generate_avatar_video.py <photo_path> <audio_path> <output_path>")
        sys.exit(1)
    generate(sys.argv[1], sys.argv[2], sys.argv[3])

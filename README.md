# Silver iPhone 6s video replacement

A locally run, semi-automatic video replacement workflow. It helps replace a black phone in a mirror selfie with a **silver iPhone 6s**, while preserving source frame rate, duration, background and (with FFmpeg) audio.

**Privacy:** Keep the original video on your computer. Do not upload personal videos to this repository. This repository is currently public.

## Requirements

- Python 3.10 or newer
- FFmpeg installed and on PATH
- Python libraries in `requirements.txt`

## Getting started

1. Download this repository as ZIP, extract it, then place your own original clip in the folder as `input.mp4`.
2. Install libraries: `python -m pip install -r requirements.txt`
3. Prepare `silver_iphone6s.png`: a transparent back view of a silver iPhone 6s. Its rear camera should appear on image-right in the mirror. Remove empty transparent margins.
4. Mark the phone's four corners, or create a `tracking.json` of phone corners (format below).
5. Run: `python replace_phone.py --input input.mp4 --phone silver_iphone6s.png --track tracking.json --output edited.mp4`

### Tracking JSON

```json
{
  "keyframes": [
    {"frame": 0, "corners": [[289,278],[379,276],[380,449],[297,449]]},
    {"frame": 30, "corners": [[294,251],[382,248],[383,436],[302,439]]}
  ]
}
```

Each corner set is in order **top-left → top-right → bottom-right → bottom-left** of the phone seen in the video; coordinates are pixel positions in the original video, not the screenshot. Add one keyframe every 5–15 video frames, more during fast motion. Corners between keyframes are interpolated. A template that doesn't match the phone's dimensions will distort.

The renderer makes a conservative attempt to preserve visible foreground fingers using skin-color segmentation. Because the face and hand may overlap, the mask may require manual correction in After Effects. Accurate replacement is not guaranteed. Check the output frame-by-frame.

## Privacy and output notes

Do not commit source or output MP4 files, extracted frames, personal screenshots or other private media. This project only stores code. Video resolution and fps are preserved, but re-encoding may slightly change image quality. With FFmpeg installed the source audio is retained.

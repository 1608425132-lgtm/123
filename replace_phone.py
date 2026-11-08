#!/usr/bin/env python3
"""Semi-automatic smartphone replacement in a mirror selfie.
Usage:
  python replace_phone.py --input input.mp4 --calibrate --track tracking.json
  python replace_phone.py --input input.mp4 --phone silver_iphone6s.png --track tracking.json --output edited.mp4
"""
import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
import cv2
import numpy as np

def calibrate(input_file, output_track, every):
    cap = cv2.VideoCapture(str(input_file))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total < 1: raise RuntimeError("Could not open input video")
    frames = list(range(0, total, every))
    if frames[-1] != total - 1: frames.append(total - 1)
    result = {}
    window = "Click UL, UR, LR, LL | n next | p previous | u undo | q save"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    idx = 0
    while 0 <= idx < len(frames):
        frame_num = frames[idx]
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        ok, frame = cap.read()
        if not ok: break
        points = result.get(frame_num, []).copy()
        def on_mouse(event, x, y, flags, userdata):
            if event == cv2.EVENT_LBUTTONDOWN and len(points) < 4:
                points.append([int(x), int(y)])
        cv2.setMouseCallback(window, on_mouse)
        while True:
            shown = frame.copy()
            cv2.putText(shown, "Frame %s / %s" % (frame_num, total - 1), (15, 35),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            for k, (x, y) in enumerate(points):
                cv2.circle(shown, (x, y), 5, (0, 255, 255), -1)
                cv2.putText(shown, str(k + 1), (x + 6, y), cv2.FONT_HERSHEY_SIMPLEX,
                            0.6, (0, 255, 255), 2)
            cv2.imshow(window, shown)
            key = cv2.waitKey(30) & 255
            if key == ord("u") and points: points.pop()
            elif key in (ord("n"), ord("p"), ord("q")):
                if len(points) == 4: result[frame_num] = points.copy()
                if key == ord("q"): idx = len(frames)
                elif key == ord("p"): idx = max(0, idx - 1)
                else: idx += 1
                break
    cv2.destroyAllWindows()
    cap.release()
    if not result: raise RuntimeError("No keyframes selected")
    output_track.write_text(json.dumps({"keyframes": [
        {"frame": k, "corners": result[k]} for k in sorted(result)
    ]}, indent=2), encoding="utf-8")
    print("Saved %d keyframes to %s" % (len(result), output_track))

def tracks(path):
    obj = json.loads(path.read_text(encoding="utf-8"))
    pts = {int(x["frame"]): np.array(x["corners"], dtype=np.float32)
           for x in obj["keyframes"]}
    if not pts: raise ValueError("No tracking keyframes")
    if any(a.shape != (4, 2) for a in pts.values()):
        raise ValueError("Each corner set must have exactly four [x,y] pairs")
    return pts

def interpolate(points, frame):
    keys = sorted(points)
    if frame <= keys[0]: return points[keys[0]]
    if frame >= keys[-1]: return points[keys[-1]]
    lo = max(x for x in keys if x <= frame)
    hi = min(x for x in keys if x >= frame)
    if lo == hi: return points[lo]
    t = float(frame - lo) / float(hi - lo)
    return (1.0 - t) * points[lo] + t * points[hi]

def skin_mask(frame):
    ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
    mask = cv2.inRange(ycrcb, (0, 129, 77), (255, 177, 135))
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.bitwise_and(mask, cv2.inRange(hsv[:, :, 1], 30, 220))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,
                            np.ones((3, 3), np.uint8))
    return cv2.GaussianBlur(mask, (5, 5), .8).astype(np.float32) / 255.

def blend(frame, phone, four_corners, preserve_fingers=True):
    h, w = frame.shape[:2]
    ph, pw = phone.shape[:2]
    source = np.float32([[0, 0], [pw - 1, 0], [pw - 1, ph - 1], [0, ph - 1]])
    H = cv2.getPerspectiveTransform(source, np.float32(four_corners))
    projected = cv2.warpPerspective(phone, H, (w, h),
                                    flags=cv2.INTER_LINEAR,
                                    borderMode=cv2.BORDER_CONSTANT)
    alpha = projected[:, :, 3].astype(np.float32) / 255.
    alpha *= 0.95
    if preserve_fingers:
        alpha *= (1. - 0.98 * skin_mask(frame))
    alpha = cv2.GaussianBlur(alpha, (3, 3), .4)
    result = frame.astype(np.float32) * (1 - alpha[:, :, None])
    result += projected[:, :, :3].astype(np.float32) * alpha[:, :, None]
    return np.uint8(np.clip(result, 0, 255))

def render(input_file, png, track_file, output_file, preserve_fingers):
    phone = cv2.imread(str(png), cv2.IMREAD_UNCHANGED)
    if phone is None: raise FileNotFoundError(str(png))
    if len(phone.shape) != 3 or phone.shape[2] != 4:
        raise ValueError("Phone PNG must have transparent alpha channel")
    control = tracks(track_file)
    cap = cv2.VideoCapture(str(input_file))
    if not cap.isOpened(): raise FileNotFoundError(str(input_file))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.
    temp = Path(tempfile.mkdtemp(prefix="phone_replace_"))
    silent = temp / "silent.mp4"
    writer = cv2.VideoWriter(str(silent), cv2.VideoWriter_fourcc(*"mp4v"),
                             fps, (w, h))
    if not writer.isOpened(): raise RuntimeError("Could not start MP4 writer")
    try:
        n = 0
        while True:
            ok, frame = cap.read()
            if not ok: break
            writer.write(blend(frame, phone, interpolate(control, n),
                               preserve_fingers))
            n += 1
        writer.release()
        cap.release()
        if n == 0: raise RuntimeError("Input video has no frames")
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                            "-i", str(silent), "-i", str(input_file),
                            "-map", "0:v:0", "-map", "1:a?",
                            "-c:v", "libx264", "-crf", "18", "-preset", "medium",
                            "-pix_fmt", "yuv420p", "-c:a", "aac",
                            "-shortest", str(output_file)], check=True)
        else:
            shutil.copy2(silent, output_file)
            print("Warning: no FFmpeg found; source audio not retained")
        print("Saved %d frames to %s" % (n, output_file))
    finally:
        writer.release()
        cap.release()
        shutil.rmtree(temp, ignore_errors=True)

def main():
    ap = argparse.ArgumentParser(description="Local silver-phone video replacement")
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--phone", type=Path, default=Path("silver_iphone6s.png"))
    ap.add_argument("--track", type=Path, default=Path("tracking.json"))
    ap.add_argument("--output", type=Path, default=Path("edited.mp4"))
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--step", type=int, default=15)
    ap.add_argument("--no-skin-mask", action="store_true")
    args = ap.parse_args()
    if args.calibrate:
        calibrate(args.input, args.track, args.step)
    else:
        render(args.input, args.phone, args.track,
               args.output, not args.no_skin_mask)

if __name__ == "__main__":
    main()

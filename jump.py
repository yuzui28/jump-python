#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import math
import os
import sys
import time

from PIL import Image, ImageDraw
import numpy as np


DEFAULT_CONFIG = {
    "area_left": 80,
    "area_top": 800,
    "area_right": 1360,
    "area_bottom": 2200,

    "offset_x": 0,
    "offset_y": 110,

    "advanced_target_mode": True,
    "advanced_square_ratio": 0.30,
    "advanced_round_ratio": 0.50,
    "round_width_threshold": 160,
    "advanced_offset_y": 0,

    "press_x": 540,
    "press_y": 1600,

    "min_press": 200,
    "max_press": 2200,

    "scan_step": 3,

    "piece_min_pixels": 80,

    "target_min_count": 5,
    "target_min_width": 30,
    "target_max_width": 560,

    "draw_debug": True,
    "wait_after_jump": 1200
}


def now_ms():
    return int(time.time() * 1000)


def load_config(path):
    cfg = dict(DEFAULT_CONFIG)

    if path and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)

            for k, v in user_cfg.items():
                cfg[k] = v
        except Exception:
            pass

    return cfg


def save_default_config(path):
    if not path or os.path.exists(path):
        return

    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def find_piece(arr, cfg):
    h, w, _ = arr.shape

    l = max(0, min(int(cfg["area_left"]), w - 1))
    t = max(0, min(int(cfg["area_top"]), h - 1))
    r = max(1, min(int(cfg["area_right"]), w))
    b = max(1, min(int(cfg["area_bottom"]), h))
    step = max(1, int(cfg["scan_step"]))

    region = arr[t:b:step, l:r:step, :]
    rr = region[:, :, 0]
    gg = region[:, :, 1]
    bb = region[:, :, 2]

    mask = (
        (rr > 35) & (rr < 95) &
        (gg > 25) & (gg < 90) &
        (bb > 45) & (bb < 145) &
        (bb > rr) &
        (bb > gg)
    )

    visited = np.zeros(mask.shape, dtype=np.bool_)
    mh, mw = mask.shape

    best = None
    best_score = -999999

    for sy in range(mh):
        for sx in range(mw):
            if visited[sy, sx] or not mask[sy, sx]:
                continue

            stack = [(sx, sy)]
            visited[sy, sx] = True

            xs = []
            ys = []

            while stack:
                x, y = stack.pop()
                xs.append(x)
                ys.append(y)

                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if nx < 0 or ny < 0 or nx >= mw or ny >= mh:
                        continue
                    if visited[ny, nx] or not mask[ny, nx]:
                        continue

                    visited[ny, nx] = True
                    stack.append((nx, ny))

            count = len(xs)
            if count < int(cfg.get("piece_min_pixels", 80)):
                continue

            real_xs = np.array(xs) * step + l
            real_ys = np.array(ys) * step + t

            minx = int(real_xs.min())
            maxx = int(real_xs.max())
            miny = int(real_ys.min())
            maxy = int(real_ys.max())

            width = maxx - minx
            height = maxy - miny

            if width < 20 or height < 35:
                continue

            if height < width * 0.7:
                continue

            center_x = int(real_xs.mean())
            center_y = int(real_ys.mean())

            lower_score = center_y * 0.8
            shape_score = height * 3 - abs(width - height * 0.55) * 2
            area_score = min(count, 5000) * 2

            score = area_score + lower_score + shape_score

            if score > best_score:
                best_score = score
                best = {
                    "count": count,
                    "minx": minx,
                    "miny": miny,
                    "maxx": maxx,
                    "maxy": maxy,
                    "width": width,
                    "height": height,
                    "center_x": center_x,
                    "center_y": center_y
                }

    if best is None:
        raise RuntimeError("未识别到可靠紫色棋子")

    minx = best["minx"]
    maxx = best["maxx"]
    miny = best["miny"]
    maxy = best["maxy"]

    bottom_band_top = max(miny, maxy - 14)
    bottom_region = arr[bottom_band_top:maxy + 1:step, minx:maxx + 1:step, :]

    br = bottom_region[:, :, 0]
    bg = bottom_region[:, :, 1]
    bb2 = bottom_region[:, :, 2]

    bmask = (
        (br > 35) & (br < 95) &
        (bg > 25) & (bg < 90) &
        (bb2 > 45) & (bb2 < 145) &
        (bb2 > br) &
        (bb2 > bg)
    )

    bys, bxs = np.where(bmask)

    if bxs.size > 0:
        bottom_x = int(np.mean(bxs * step + minx))
        bottom_count = int(bxs.size)
    else:
        bottom_x = int((minx + maxx) / 2)
        bottom_count = 0

    return {
        "x": int(bottom_x),
        "y": int(maxy),
        "center_x": int(best["center_x"]),
        "center_y": int(best["center_y"]),
        "minx": int(minx),
        "miny": int(miny),
        "maxx": int(maxx),
        "maxy": int(maxy),
        "width": int(best["width"]),
        "height": int(best["height"]),
        "count": int(best["count"]),
        "bottom_count": int(bottom_count)
    }


def color_diff_row(row, bg):
    return (
        np.abs(row[:, 0].astype(np.int16) - int(bg[0])) +
        np.abs(row[:, 1].astype(np.int16) - int(bg[1])) +
        np.abs(row[:, 2].astype(np.int16) - int(bg[2]))
    )


def target_mask_row(row, bg):
    rr = row[:, 0]
    gg = row[:, 1]
    bb = row[:, 2]

    piece = (
        (rr > 35) & (rr < 95) &
        (gg > 25) & (gg < 90) &
        (bb > 45) & (bb < 145) &
        (bb > rr) &
        (bb > gg)
    )

    black = (rr < 18) & (gg < 18) & (bb < 18)
    white = (rr > 220) & (gg > 220) & (bb > 220)

    diff = color_diff_row(row, bg)

    return (~piece) & (~black) & (((white) & (diff > 35)) | ((~white) & (diff > 28)))


def best_segment_from_mask(mask, xs, cfg, piece, y):
    best = None
    start_i = -1
    count = 0

    def flush(end_i):
        nonlocal best, start_i, count

        if start_i >= 0 and count > 0:
            left = int(xs[start_i])
            right = int(xs[end_i])
            width = right - left
            center = int((left + right) / 2)

            if (
                count >= int(cfg["target_min_count"]) and
                width >= int(cfg["target_min_width"]) and
                width <= int(cfg["target_max_width"]) and
                abs(center - int(piece["x"])) > 80
            ):
                score = count * 10 + width

                if best is None or score > best["score"]:
                    best = {
                        "left": left,
                        "right": right,
                        "center": center,
                        "count": int(count),
                        "width": int(width),
                        "score": int(score),
                        "y": int(y)
                    }

        start_i = -1
        count = 0

    for i, ok in enumerate(mask):
        x = int(xs[i])

        if abs(x - int(piece["x"])) < 140 and abs(int(y) - int(piece["y"])) < 260:
            if start_i >= 0:
                flush(i - 1)
            continue

        if bool(ok):
            if start_i < 0:
                start_i = i
            count += 1
        else:
            if start_i >= 0:
                flush(i - 1)

    if start_i >= 0:
        flush(len(mask) - 1)

    return best


def calc_advanced_target_point(target, cfg):
    left = int(target["left"])
    right = int(target["right"])
    top = int(target["top"])
    width = max(1, right - left)

    center_x = int((left + right) / 2)

    if width < int(cfg.get("round_width_threshold", 160)):
        center_y = int(top + width * float(cfg.get("advanced_round_ratio", 0.50)))
        mode = "round"
    else:
        center_y = int(top + width * float(cfg.get("advanced_square_ratio", 0.30)))
        mode = "square"

    center_y += int(cfg.get("advanced_offset_y", 0))

    return center_x, center_y, mode


def find_target(arr, cfg, piece):
    h, w, _ = arr.shape

    l = max(0, min(int(cfg["area_left"]), w - 1))
    t = max(0, min(int(cfg["area_top"]), h - 1))
    r = max(1, min(int(cfg["area_right"]), w))
    b = max(1, min(int(cfg["area_bottom"]), h))
    step = max(1, int(cfg["scan_step"]))

    xs = np.arange(l, r, step)

    chosen = None
    contour_left = []
    contour_right = []

    for y in range(t, b, step):
        if y >= int(piece["y"]) - 80:
            break

        bg = arr[y, w // 2]
        row = arr[y, xs]
        mask = target_mask_row(row, bg)

        seg = best_segment_from_mask(mask, xs, cfg, piece, y)
        if seg is not None:
            chosen = seg
            break

    if chosen is None:
        raise RuntimeError("未识别到目标顶部边缘")

    zero_x = int((chosen["left"] + chosen["right"]) / 2)
    zero_y = int(chosen["y"])

    last_left = chosen["left"]
    last_right = chosen["right"]

    for yy in range(zero_y, min(zero_y + 160, b), step):
        if yy >= int(piece["y"]) - 60:
            break

        bg = arr[yy, w // 2]
        row = arr[yy, xs]
        mask = target_mask_row(row, bg)

        seg = best_segment_from_mask(mask, xs, cfg, piece, yy)

        if seg is not None:
            if abs(seg["left"] - last_left) < 120 and abs(seg["right"] - last_right) < 120:
                contour_left.append((int(seg["left"]), int(yy)))
                contour_right.append((int(seg["right"]), int(yy)))
                last_left = seg["left"]
                last_right = seg["right"]

    if bool(cfg.get("advanced_target_mode", False)):
        final_x, final_y, target_mode = calc_advanced_target_point(
            {
                "left": chosen["left"],
                "right": chosen["right"],
                "top": zero_y
            },
            cfg
        )
        final_x += int(cfg.get("offset_x", 0))
    else:
        final_x = zero_x + int(cfg.get("offset_x", 0))
        final_y = zero_y + int(cfg.get("offset_y", 110))
        target_mode = "normal"

    return {
        "zero_x": int(zero_x),
        "zero_y": int(zero_y),
        "x": int(final_x),
        "y": int(final_y),
        "left": int(chosen["left"]),
        "right": int(chosen["right"]),
        "top": int(zero_y),
        "count": int(chosen["count"]),
        "width": int(chosen["width"]),
        "mode": target_mode,
        "contour_left": contour_left,
        "contour_right": contour_right
    }


def draw_cross(draw, x, y, size, color, width=4):
    draw.line((x - size, y, x + size, y), fill=color, width=width)
    draw.line((x, y - size, x, y + size), fill=color, width=width)


def draw_debug(img, cfg, piece, target, result, debug_path):
    draw = ImageDraw.Draw(img)

    draw.rectangle(
        [cfg["area_left"], cfg["area_top"], cfg["area_right"], cfg["area_bottom"]],
        outline=(255, 150, 0),
        width=4
    )

    draw.rectangle(
        [piece["minx"], piece["miny"], piece["maxx"], piece["maxy"]],
        outline=(255, 0, 0),
        width=4
    )

    draw_cross(draw, piece["x"], piece["y"], 50, (255, 0, 0), 4)

    draw.line(
        [target["left"], target["top"], target["right"], target["top"]],
        fill=(0, 220, 80),
        width=5
    )

    cl = target.get("contour_left") or []
    cr = target.get("contour_right") or []

    if len(cl) >= 2:
        draw.line(cl, fill=(0, 220, 80), width=3)

    if len(cr) >= 2:
        draw.line(cr, fill=(0, 220, 80), width=3)

    draw_cross(draw, target["zero_x"], target["zero_y"], 45, (0, 80, 255), 4)
    draw_cross(draw, target["x"], target["y"], 55, (0, 220, 80), 4)

    draw.line(
        [piece["x"], piece["y"], target["x"], target["y"]],
        fill=(0, 200, 255),
        width=4
    )

    os.makedirs(os.path.dirname(debug_path), exist_ok=True)
    img.save(debug_path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--debug", required=True)
    args = parser.parse_args()

    save_default_config(args.config)
    cfg = load_config(args.config)

    start = now_ms()

    img = Image.open(args.input).convert("RGB")
    arr = np.asarray(img)

    piece = find_piece(arr, cfg)
    target = find_target(arr, cfg, piece)

    dx = int(piece["x"]) - int(target["x"])
    dy = int(piece["y"]) - int(target["y"])
    distance = math.sqrt(dx * dx + dy * dy)

    press_ms = int(distance)
    press_ms = max(int(cfg["min_press"]), min(int(cfg["max_press"]), press_ms))

    result = {
        "ok": True,
        "engine": "python_numpy_pillow",
        "target_mode": target["mode"],

        "piece_x": int(piece["x"]),
        "piece_y": int(piece["y"]),
        "piece_center_x": int(piece["center_x"]),
        "piece_center_y": int(piece["center_y"]),
        "piece_box": [int(piece["minx"]), int(piece["miny"]), int(piece["maxx"]), int(piece["maxy"])],
        "piece_pixels": int(piece["count"]),

        "target_zero_x": int(target["zero_x"]),
        "target_zero_y": int(target["zero_y"]),
        "target_x": int(target["x"]),
        "target_y": int(target["y"]),
        "target_edge": [int(target["left"]), int(target["top"]), int(target["right"]), int(target["top"])],
        "target_pixels": int(target["count"]),

        "distance": round(float(distance), 2),
        "press_ms": int(press_ms),
        "press_x": int(cfg["press_x"]),
        "press_y": int(cfg["press_y"]),

        "debug_img": args.debug,
        "elapsed_ms": now_ms() - start
    }

    if bool(cfg.get("draw_debug", True)):
        draw_debug(img, cfg, piece, target, result, args.debug)

    write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        out = None

        if "--output" in sys.argv:
            try:
                out = sys.argv[sys.argv.index("--output") + 1]
            except Exception:
                out = None

        result = {
            "ok": False,
            "engine": "python_numpy_pillow",
            "error": str(e)
        }

        if out:
            write_json(out, result)

        print(json.dumps(result, ensure_ascii=False))
        sys.exit(1)
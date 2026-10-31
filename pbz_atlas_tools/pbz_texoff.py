"""对单张贴图扫描像素起点，打印各偏移的解码平滑度（越小越清晰）。"""
import struct
import sys

import numpy as np
import texture2ddecoder as t2d


def score(bgra, w, h):
    a = np.frombuffer(bgra, dtype=np.uint8).reshape(h, w, 4).astype(np.int16)
    rgb, al = a[:, :, :3], a[:, :, 3]
    m = al > 8
    if m.sum() < w * h * 0.02:
        return 999.0, float(m.mean())
    dx = np.abs(np.diff(rgb, axis=1)).mean(axis=2)
    m2 = m[:, 1:] & m[:, :-1]
    return (float(dx[m2].mean()) if m2.any() else 999.0), float(m.mean())


def main(path):
    d = open(path, 'rb').read()
    head = struct.unpack_from('<I', d, 4)[0]
    body = d[head:]
    n = len(body)
    side = 0
    for s in (2048, 1024, 512, 256, 128, 64):
        if s * s <= n:
            side = s
            break
    print(f'{path.rsplit(chr(92), 1)[-1]}  body={n}  side={side}')
    best = []
    for off in range(0, min(96, n - side * side) + 1):
        try:
            s, cov = score(t2d.decode_bc7(body[off:off + side * side], side, side), side, side)
        except Exception:
            continue
        best.append((s, off, cov))
    best.sort()
    for s, off, cov in best[:6]:
        print(f'  score={s:7.2f} off={off:<3} 覆盖率={cov:.2f}')


if __name__ == '__main__':
    for p in sys.argv[1:]:
        main(p)

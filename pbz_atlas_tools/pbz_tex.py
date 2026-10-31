"""把容器里抽出的 UI 贴图（Zen 包内联像素）解码成 PNG。

BC7 数据长度 = 宽 × 高（1 字节/像素），因此可由数据长度反推尺寸：
优先取 2 的幂组合，其次用平方根。
"""
import os
import struct
import sys

import texture2ddecoder as t2d
from PIL import Image

FMT = {'bc7': t2d.decode_bc7, 'bc3': t2d.decode_bc3,
       'bc5': t2d.decode_bc5, 'bc1': t2d.decode_bc1}


def guess_dims(n):
    """由字节数推断 (w, h, mips)；BC7 为 1 字节/像素。"""
    for mips in (0, 1):
        total = n
        if mips:  # 完整 mip 链总字节 ≈ w*h*4/3
            base = int(n * 3 / 4)
        else:
            base = n
        for w in (2048, 1024, 512, 256, 128, 64):
            h = base // w
            if w * h == base and h in (2048, 1024, 512, 256, 128, 64):
                return w, h, bool(mips)
    s = int(n ** 0.5)
    return s, s, False


def decode(path, out, fmt='bc7', dims=None):
    d = open(path, 'rb').read()
    head = struct.unpack_from('<I', d, 4)[0]
    body = d[head:]
    if dims:
        w, h = dims
    else:
        w, h, _ = guess_dims(len(body))
    need = w * h
    pix = body[-need:] if len(body) >= need else body
    bgra = FMT[fmt](pix, w, h)
    im = Image.frombytes('RGBA', (w, h), bgra, 'raw', 'BGRA')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    im.save(out)
    return w, h, len(body)


if __name__ == '__main__':
    src = sys.argv[1]
    dst = sys.argv[2]
    fmt = sys.argv[3] if len(sys.argv) > 3 else 'bc7'
    print(decode(src, dst, fmt), '→', dst)

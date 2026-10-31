"""图鉴成品质量检查：用「相邻像素差」判定图标是清晰图还是噪点遮罩。

清晰贴图相邻像素接近，score 低；白模/噪点遮罩 score 高。
"""
import glob
import os
import sys

import numpy as np
from PIL import Image

from .config import ICONS as D, ATLAS  # noqa: E402


def score(path):
    im = Image.open(path).convert('RGBA')
    a = np.asarray(im).astype(np.int16)
    rgb, alpha = a[:, :, :3], a[:, :, 3]
    mask = alpha > 8
    if mask.sum() < 64:
        return 0.0, float(mask.mean())
    dx = np.abs(np.diff(rgb, axis=1)).mean(axis=2)
    m2 = mask[:, 1:] & mask[:, :-1]
    return float(dx[m2].mean()) if m2.any() else 0.0, float(mask.mean())


def main():
    files = sorted(glob.glob(os.path.join(D, '*.png')))
    res = [(score(p)[0], score(p)[1], os.path.basename(p)) for p in files]
    res.sort(reverse=True)
    vals = np.array([r[0] for r in res])
    print(f'共 {len(res)} 张  中位数={np.median(vals):.2f}  '
          f'90分位={np.percentile(vals, 90):.2f}  最大={vals.max():.2f}')
    print('\n噪点最重的 15 张：')
    for s, cov, n in res[:15]:
        print(f'  {s:7.2f}  覆盖率={cov:.2f}  {n}')
    thr = float(sys.argv[1]) if len(sys.argv) > 1 else 12.0
    bad = [r for r in res if r[0] > thr]
    print(f'\n超过阈值 {thr} 的 {len(bad)} 张已写入 export/atlas/_noise.txt')
    open(os.path.join(ATLAS, '_noise.txt'), 'w', encoding='utf-8').write(
        '\n'.join(f'{s:.2f}\t{n}' for s, _, n in bad))


if __name__ == '__main__':
    main()

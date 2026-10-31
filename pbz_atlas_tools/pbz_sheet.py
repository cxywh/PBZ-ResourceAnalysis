"""把图鉴图标拼成一张总览图（带中文名与 ID），用于快速核对。"""
import csv
import os
import sys

from PIL import Image, ImageDraw, ImageFont

from .config import ATLAS as AT  # noqa: E402
FONT = r'C:\Windows\Fonts\msyh.ttc'
COLS, CELL, PAD, TOP = 8, 128, 12, 46
CAP = 34


def font(sz):
    try:
        return ImageFont.truetype(FONT, sz)
    except Exception:
        return ImageFont.load_default()


def main(out, cats):
    rows = list(csv.DictReader(open(os.path.join(AT, 'index.csv'), encoding='utf-8-sig')))
    rows = [r for r in rows if r['PNG'] and r['分类'] in cats]
    if not rows:
        print('无可拼条目'); return
    n = len(rows)
    cols = min(COLS, n)
    lines = (n + cols - 1) // cols
    W = PAD + cols * (CELL + PAD)
    H = TOP + lines * (CELL + CAP + PAD) + PAD
    im = Image.new('RGB', (W, H), (20, 22, 26))
    dr = ImageDraw.Draw(im)
    title = ' + '.join(cats) + f'  {n} 条'
    dr.text((PAD, 14), title, font=font(20), fill=(232, 230, 227))
    f = font(13)
    for i, r in enumerate(rows):
        c, ln = i % cols, i // cols
        x = PAD + c * (CELL + PAD)
        y = TOP + ln * (CELL + CAP + PAD)
        try:
            ic = Image.open(os.path.join(AT, r['PNG'])).convert('RGBA').resize((CELL, CELL), Image.LANCZOS)
        except Exception:
            continue
        bg = Image.new('RGBA', (CELL, CELL), (36, 40, 48, 255))
        bg.alpha_composite(ic)
        im.paste(bg.convert('RGB'), (x, y))
        nm = r['中文名'][:11]
        dr.text((x, y + CELL + 3), nm, font=f, fill=(226, 224, 220))
        dr.text((x, y + CELL + 19), r['ID'][:15], font=font(11), fill=(127, 211, 161))
    im.save(out)
    print(f'{n} 条 → {out}  {im.size}')


if __name__ == '__main__':
    out = sys.argv[1]
    cats = sys.argv[2].split(',') if len(sys.argv) > 2 else ['武器', '物品', '配饰']
    main(out, cats)

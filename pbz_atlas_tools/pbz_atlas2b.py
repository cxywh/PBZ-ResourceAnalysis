"""图鉴后处理：分类（彩色/剪影）、转剪影、出 HTML、拼图、打包。

依赖 pbz_atlas.py 已生成 icons/ 与 index.csv。
"""
import base64
import csv
import io
import os
import sys
import zipfile

import numpy as np
from PIL import Image

from .config import ATLAS as AT, ICONS, EX  # noqa: E402
THUMB = 128


def metrics(im):
    a = np.asarray(im.convert('RGBA')).astype(np.int16)
    rgb, al = a[:, :, :3], a[:, :, 3]
    m = al > 8
    cov = float(m.mean())
    if m.sum() < 64:
        return 999.0, cov
    dx = np.abs(np.diff(rgb, axis=1)).mean(axis=2)
    m2 = m[:, 1:] & m[:, :-1]
    return (float(dx[m2].mean()) if m2.any() else 999.0), cov


def silhouette(im):
    a = np.asarray(im.convert('RGBA')).copy()
    a[:, :, 0] = a[:, :, 1] = a[:, :, 2] = 245
    return Image.fromarray(a, 'RGBA')


def main():
    rows = list(csv.DictReader(open(os.path.join(AT, 'index.csv'), encoding='utf-8-sig')))
    keep, drop = [], 0
    for r in rows:
        p = os.path.join(AT, r['PNG'])
        if not r['PNG'] or not os.path.exists(p):
            drop += 1
            continue
        im = Image.open(p)
        s, cov = metrics(im)
        if cov < 0.97 and s < 18:
            r['类'] = '彩色'
            keep.append(r)
        elif cov < 0.97:
            silhouette(im).save(p)
            r['类'] = '剪影'
            keep.append(r)
        else:
            drop += 1
    col = sum(1 for r in keep if r['类'] == '彩色')
    print(f'保留 {len(keep)}（彩色 {col} / 剪影 {len(keep) - col}），丢弃 {drop}')

    with open(os.path.join(AT, 'index.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['分类', '中文名', 'ID', '资产', 'chunk', 'PNG', '尺寸', '类型'])
        for r in keep:
            w.writerow([r['分类'], r['中文名'], r['ID'], r['资产'], r['chunk'],
                        r['PNG'], r['尺寸'], r['类']])

    cards = []
    for r in keep:
        im = Image.open(os.path.join(AT, r['PNG'])).convert('RGBA')
        buf = io.BytesIO()
        im.resize((THUMB, THUMB), Image.LANCZOS).save(buf, 'PNG', optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode()
        badge = '' if r['类'] == '彩色' else '<span class="sil">剪影</span>'
        cards.append(
            f'<figure><img src="data:image/png;base64,{b64}" width="{THUMB}" height="{THUMB}" alt="{r["中文名"]}">'
            f'<figcaption><b>{r["中文名"]}</b><span class="id">{r["ID"]}</span>'
            f'<span class="sub">{r["分类"]} · {r["尺寸"]}px {badge}</span></figcaption></figure>')
    html = """<!doctype html><html lang="zh"><meta charset="utf-8"><title>PBZ 图鉴</title>
<style>
body{margin:0;padding:24px;background:#14161a;color:#e8e6e3;font:14px/1.5 "Segoe UI","Microsoft YaHei",sans-serif}
h1{font-size:20px;font-weight:600;margin:0 0 4px}
.meta{color:#8b9098;font-size:12px;margin-bottom:18px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px}
figure{margin:0;background:#1d2026;border:1px solid #2a2e36;border-radius:8px;padding:10px;text-align:center}
figure img{width:128px;height:128px;background:repeating-conic-gradient(#242830 0% 25%,#1d2026 0% 50%) 50%/16px 16px;border-radius:6px}
figcaption{margin-top:8px;display:flex;flex-direction:column;gap:2px}
figcaption b{font-size:13px;font-weight:600}
.id{font-family:Consolas,monospace;font-size:11px;color:#7fd3a1;word-break:break-all}
.sub{font-size:11px;color:#6f7681}
.sil{color:#c9a227}
</style>
<h1>Phantom Blade Zero 图鉴</h1>
<div class="meta">__M__</div>
<div class="grid">__C__</div></html>"""
    meta = (f'共 {len(keep)} 条 · 彩色图标 {col} 条 · 剪影 {len(keep) - col} 条'
            f'（原图只有形状遮罩，游戏内由 UI 着色）· 贴图由容器 BC7 直接解码')
    html = html.replace('__M__', meta).replace('__C__', '\n'.join(cards))
    open(os.path.join(AT, 'atlas.html'), 'w', encoding='utf-8').write(html)
    print(f'HTML {len(html) / 1048576:.1f} MB')

    from .pbz_sheet import main as sheet
    for cats, out in ((['武器'], 'atlas_sheet_weapon.png'),
                      (['配饰'], 'atlas_sheet_accessory.png'),
                      (['物品'], 'atlas_sheet_item.png')):
        try:
            sheet(os.path.join(EX, out), cats)
        except Exception as ex:
            print('拼图失败', cats, ex)

    used = {os.path.basename(r['PNG']) for r in keep}
    for fn in os.listdir(ICONS):
        if fn not in used:
            try:
                os.remove(os.path.join(ICONS, fn))
            except OSError:
                pass
    zp = os.path.join(EX, 'pbz_atlas.zip')
    with zipfile.ZipFile(zp, 'w', zipfile.ZIP_DEFLATED) as z:
        for root, _, fs in os.walk(AT):
            for fn in fs:
                fp = os.path.join(root, fn)
                z.write(fp, os.path.relpath(fp, AT))
    print(f'ZIP {os.path.getsize(zp) / 1048576:.1f} MB')


if __name__ == '__main__':
    main()

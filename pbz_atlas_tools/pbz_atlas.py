"""从容器批量取图标并生成图鉴（PNG + 自包含 HTML）。

用法： python pbz_atlas.py [weapon|inventory|accessory|all] [--limit N]
"""
import base64
import csv
import io
import os
import struct
import sys
from collections import Counter

import texture2ddecoder as t2d
from PIL import Image

from .pbz_ucas import Toc  # noqa: E402

from .config import UTOC, VAL, OUT  # noqa: E402
THUMB = 128
PIX_OFF = 3  # 实测：导出体前缀 3 字节，之后是 BC7 像素


def load_rows(table):
    p = os.path.join(VAL, f'{table}.csv')
    if not os.path.exists(p):
        return []
    rows = list(csv.reader(open(p, encoding='utf-8-sig')))
    hdr, data = rows[0], rows[1:]
    return [dict(zip(hdr, r)) for r in data if len(r) == len(hdr)]


def pick(row, kind, freq=None):
    """从一行里挑出 (中文名, 主键, 图标资产路径)。

    优先级：彩色成品图 > 白模遮罩；被大量行共用的通用图降权。
    """
    names = [k for k in row if k.endswith('[N]') and row[k]]
    vals = [row[k] for k in names]
    ident = next((v for v in vals if '/' not in v), None)

    def rank(v):
        b = v.rsplit('/', 1)[-1]
        r = 0
        if b.endswith('_w'):
            r += 100
        if '/White/' in v:
            r += 40
        if freq and freq.get(b, 0) >= 10:
            r += 80
        if '/items/' in v:
            r -= 10
        if '/UINew/' in v:
            r -= 5
        if b.startswith('T_'):
            r -= 3
        if 'Icon' in b:
            r -= 2
        return r

    icons = [v for v in vals if v.startswith('/Game/')]
    icons.sort(key=rank)
    return row.get('row', ''), ident, (icons[0] if icons else None)


CATS = {
    'weapon': ('DT_WeaponData', '武器'),
    'inventory': ('DT_InventoryData', '物品'),
    'accessory': ('DT_Accessory', '配饰'),
}


def candidates(icon_path):
    base = icon_path.rsplit('/', 1)[-1]
    out = []
    for pre, rep in (('Icon_Hud_Weapon_', 'T_Icon_Weapon_'),
                     ('Icon_Hud_', 'T_Icon_'),
                     ('Icon_', 'T_Icon_')):
        if base.startswith(pre):
            out.append(rep + base[len(pre):])
    out += [base, 'T_' + base, 'T_Icon_' + base]
    seen, uniq = set(), []
    for n in out:
        if n not in seen:
            seen.add(n)
            uniq.append(n)
    return uniq


def decode(data):
    """返回 PIL.Image 或 None。"""
    if len(data) < 1024:
        return None
    head = struct.unpack_from('<I', data, 4)[0]
    body = data[head:]
    n = len(body) - PIX_OFF
    side = 0
    for s in (2048, 1024, 512, 256, 128, 64):
        if s * s <= n:
            side = s
            break
    if not side:
        return None
    px = body[PIX_OFF:PIX_OFF + side * side]
    bgra = t2d.decode_bc7(px, side, side)
    return Image.frombytes('RGBA', (side, side), bgra, 'raw', 'BGRA')


def main():
    want = sys.argv[1] if len(sys.argv) > 1 else 'all'
    limit = None
    if '--limit' in sys.argv:
        limit = int(sys.argv[sys.argv.index('--limit') + 1])
    print('解析容器目录…')
    t = Toc(UTOC)
    pmap = t.paths()
    suffix = {}
    for k, v in pmap.items():
        suffix.setdefault(k.rsplit('/', 1)[-1], v)
    print(f'  资产 {len(pmap):,} 条')

    entries, missing = [], []
    cats = CATS if want == 'all' else {want: CATS[want]}
    for cat, (table, label) in cats.items():
        rows = load_rows(table)
        print(f'{label}({table})  {len(rows)} 行')
        freq = Counter()
        for r in rows:
            for v in r.values():
                if v.startswith('/Game/'):
                    freq[v.rsplit('/', 1)[-1]] += 1
        for r in rows[:limit] if limit else rows:
            zh, ident, icon = pick(r, cat, freq)
            if not icon:
                missing.append((label, zh, ident, '无图标路径'))
                continue
            hit = None
            for c in candidates(icon):
                idx = suffix.get(c + '.uasset')
                if idx is not None:
                    hit = (c, idx)
                    break
            if not hit:
                missing.append((label, zh, ident, icon.rsplit('/', 1)[-1]))
                continue
            entries.append({'cat': cat, 'label': label, 'zh': zh, 'id': ident or '',
                            'asset': hit[0], 'chunk': hit[1]})

    print(f'待解码 {len(entries)} 条，缺图 {len(missing)} 条')
    os.makedirs(os.path.join(OUT, 'icons'), exist_ok=True)
    ok = 0
    for i, e in enumerate(entries):
        try:
            data = t.read_chunk(e['chunk'])
            im = decode(data)
        except Exception as ex:
            im = None
            e['err'] = str(ex)[:60]
        if im is None:
            e['png'] = None
            continue
        fn = f"{e['cat']}_{e['asset']}.png"
        im.save(os.path.join(OUT, 'icons', fn))
        e['png'] = f"icons/{fn}"
        e['side'] = im.width
        buf = io.BytesIO()
        im.convert('RGBA').resize((THUMB, THUMB), Image.LANCZOS).save(buf, 'PNG', optimize=True)
        e['thumb'] = base64.b64encode(buf.getvalue()).decode()
        ok += 1
        if (i + 1) % 50 == 0:
            print(f'  {i + 1}/{len(entries)}…')

    with open(os.path.join(OUT, 'index.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['分类', '中文名', 'ID', '资产', 'chunk', 'PNG', '尺寸'])
        for e in entries:
            w.writerow([e['label'], e['zh'], e['id'], e['asset'], e['chunk'],
                        e.get('png') or '', e.get('side') or ''])
    write_html(entries, missing)
    print(f'完成：{ok}/{len(entries)} 张成功，缺图 {len(missing)} 条 → {OUT}')


def write_html(entries, missing):
    cards = []
    for e in entries:
        if not e.get('thumb'):
            continue
        cards.append(
            f'<figure><img src="data:image/png;base64,{e["thumb"]}" width="{THUMB}" height="{THUMB}" '
            f'style="image-rendering:auto" alt="{e["zh"]}">'
            f'<figcaption><b>{e["zh"]}</b><span class="id">{e["id"]}</span>'
            f'<span class="sub">{e["label"]} · {e.get("side", 0)}px</span></figcaption></figure>')

    html = """<!doctype html><html lang="zh"><meta charset="utf-8"><title>PBZ 图鉴</title>
<style>
body{margin:0;padding:24px;background:#14161a;color:#e8e6e3;font:14px/1.5 "Segoe UI","Microsoft YaHei",sans-serif}
h1{font-size:20px;font-weight:600;margin:0 0 4px}
.meta{color:#8b9098;font-size:12px;margin-bottom:18px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px}
figure{margin:0;background:#1d2026;border:1px solid #2a2e36;border-radius:8px;padding:10px;text-align:center}
figure img{width:128px;height:128px;background:
 repeating-conic-gradient(#242830 0% 25%,#1d2026 0% 50%) 50%/16px 16px;border-radius:6px}
figcaption{margin-top:8px;display:flex;flex-direction:column;gap:2px}
figcaption b{font-size:13px;font-weight:600}
.id{font-family:Consolas,monospace;font-size:11px;color:#7fd3a1;word-break:break-all}
.sub{font-size:11px;color:#6f7681}
</style>
<h1>Phantom Blade Zero 图鉴</h1>
<div class="meta">武器 / 物品 / 配饰 · 图标由容器内 BC7 贴图直接解码 · 共 __N__ 条</div>
<div class="grid">__CARDS__</div></html>"""
    html = html.replace('__N__', str(len(cards))).replace('__CARDS__', '\n'.join(cards))
    open(os.path.join(OUT, 'atlas.html'), 'w', encoding='utf-8').write(html)
    print('HTML →', os.path.join(OUT, 'atlas.html'), f'{len(html) / 1048576:.1f} MB')


if __name__ == '__main__':
    main()

"""PBZ 版本 diff 工具。

三个子命令：
  snap <名字>        生成当前状态的快照 JSON（构建号 + 表集合 + 资产哈希 + 图鉴清单）
  diff <a> <b>       比对两份快照，输出新增/删除/变更（真正的版本 diff）
  coverage <名字>    比对同一份快照内部的两套采集口径：容器侧 vs 运行时

用法：
  python pbz_diff.py snap v26266538
  python pbz_diff.py coverage v26266538
  python pbz_diff.py diff v26266538 v27000000
"""
import csv
import hashlib
import json
import os
import re
import sys
import time

from .config import EX, SNAPDIR, ACF, ASSETS, RUNTIME  # noqa: E402
ATLAS = os.path.join(EX, 'atlas', 'index.csv')

DT_RE = re.compile(r'([^/\\]+)\.uasset$')


def build_id():
    try:
        t = open(ACF, encoding='utf-8', errors='ignore').read()
        return re.search(r'"buildid"\s+"(\d+)"', t).group(1)
    except Exception:
        return 'unknown'


def md5_lines(lines):
    h = hashlib.md5()
    for x in sorted(lines):
        h.update(x.encode('utf-8', 'ignore'))
        h.update(b'\n')
    return h.hexdigest()


def runtime_tables():
    out = {}
    if not os.path.exists(RUNTIME):
        return out
    for r in csv.DictReader(open(RUNTIME, encoding='utf-8-sig')):
        try:
            out[r['table']] = int(r['rows'])
        except (KeyError, ValueError):
            continue
    return out


def container_tables():
    out = set()
    with open(ASSETS, encoding='utf-8', errors='ignore') as f:
        for line in f:
            m = DT_RE.search(line.strip())
            if not m:
                continue
            n = m.group(1)
            if n.startswith('DT_') or ('/DataTable/' in line and 'Table' in n):
                out.add(n)
    return out


def atlas_assets():
    if not os.path.exists(ATLAS):
        return []
    return sorted({r['资产'] for r in csv.DictReader(open(ATLAS, encoding='utf-8-sig')) if r.get('资产')})


def cmd_snap(name):
    os.makedirs(SNAPDIR, exist_ok=True)
    rt = runtime_tables()
    ct = container_tables()
    assets = [ln.strip() for ln in open(ASSETS, encoding='utf-8', errors='ignore') if ln.strip()]
    snap = {
        'build': build_id(),
        'generated': time.strftime('%Y-%m-%d %H:%M:%S'),
        'runtime_tables': rt,
        'container_tables': sorted(ct),
        'assets_count': len(assets),
        'assets_md5': md5_lines(assets),
        'atlas_assets': atlas_assets(),
    }
    p = os.path.join(SNAPDIR, name + '.json')
    json.dump(snap, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'快照 → {p}')
    print(f'  构建号 {snap["build"]}  运行时表 {len(rt)}  容器表 {len(ct)}  '
          f'资产 {snap["assets_count"]:,}  图鉴资产 {len(snap["atlas_assets"])}')


def load(name):
    p = name if name.endswith('.json') else os.path.join(SNAPDIR, name + '.json')
    return json.load(open(p, encoding='utf-8')), os.path.basename(p)


def cmd_coverage(name):
    s, _ = load(name)
    rt, ct = set(s['runtime_tables']), set(s['container_tables'])
    only_c = sorted(ct - rt)
    only_r = sorted(rt - ct)
    print(f'构建号 {s["build"]}')
    print(f'容器侧 {len(ct)} 张 / 运行时 {len(rt)} 张 / 交集 {len(ct & rt)} 张')
    print(f'\n仅容器有（运行时未加载或已被剔除）{len(only_c)} 张：')
    for t in only_c[:30]:
        print('  -', t)
    if len(only_c) > 30:
        print(f'  … 其余 {len(only_c) - 30} 张见 JSON')
    print(f'\n仅运行时有（容器路径未命中，多为内嵌或改名）{len(only_r)} 张：')
    for t in only_r[:30]:
        print('  +', t)
    out = os.path.join(EX, f'_口径差异_{name}.md')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(f'# 采集口径差异（构建 {s["build"]}）\n\n')
        f.write(f'- 容器侧表：{len(ct)}\n- 运行时表：{len(rt)}\n- 交集：{len(ct & rt)}\n\n')
        f.write(f'## 仅容器有（{len(only_c)}）\n' + '\n'.join(f'- `{t}`' for t in only_c))
        f.write(f'\n\n## 仅运行时有（{len(only_r)}）\n' + '\n'.join(f'- `{t}`' for t in only_r))
    print(f'\n明细 → {out}')


def cmd_diff(a, b):
    A, an = load(a)
    B, bn = load(b)
    print(f'{an} 构建 {A["build"]}  →  {bn} 构建 {B["build"]}')
    lines = [f'# 版本 diff：{A["build"]} → {B["build"]}',
             f'\n生成 {time.strftime("%Y-%m-%d %H:%M:%S")}\n']

    for key, label in (('runtime_tables', '运行时表集合'), ('container_tables', '容器表集合')):
        sa = set(A[key]) if isinstance(A[key], list) else set(A[key])
        sb = set(B[key]) if isinstance(B[key], list) else set(B[key])
        add, rem = sorted(sb - sa), sorted(sa - sb)
        print(f'{label}: 新增 {len(add)} / 删除 {len(rem)}')
        lines.append(f'## {label}\n\n新增 {len(add)} 张，删除 {len(rem)} 张\n')
        for t in add[:60]:
            lines.append(f'- ➕ `{t}`')
        for t in rem[:60]:
            lines.append(f'- ➖ `{t}`')

    ra, rb = A['runtime_tables'], B['runtime_tables']
    chg = [(t, ra[t], rb[t]) for t in ra if t in rb and ra[t] != rb[t]]
    chg.sort(key=lambda x: -abs(x[2] - x[1]))
    print(f'行数变化的表: {len(chg)}')
    lines.append(f'\n## 行数变化（{len(chg)} 张，按变化量排序）\n')
    for t, x, y in chg[:80]:
        lines.append(f'- `{t}`: {x} → {y} ({y - x:+d})')

    same_assets = A['assets_md5'] == B['assets_md5']
    print(f'资产清单: {"无变化" if same_assets else "有变化"} '
          f'({A["assets_count"]:,} → {B["assets_count"]:,})')
    lines.append(f'\n## 资产清单\n\n{A["assets_count"]:,} → {B["assets_count"]:,}'
                 f'，{"哈希一致（无增删）" if same_assets else "哈希不一致（有增删）"}')

    sa, sb = set(A['atlas_assets']), set(B['atlas_assets'])
    print(f'图鉴资产: 新增 {len(sb - sa)} / 移除 {len(sa - sb)}')
    lines.append(f'\n## 图鉴资产\n\n新增 {len(sb - sa)}，移除 {len(sa - sb)}\n')
    for t in sorted(sb - sa)[:40]:
        lines.append(f'- ➕ `{t}`')
    for t in sorted(sa - sb)[:40]:
        lines.append(f'- ➖ `{t}`')

    out = os.path.join(EX, f'_版本diff_{A["build"]}_to_{B["build"]}.md')
    open(out, 'w', encoding='utf-8').write('\n'.join(lines))
    print(f'报告 → {out}')


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    cmd = sys.argv[1]
    if cmd == 'snap':
        cmd_snap(sys.argv[2])
    elif cmd == 'coverage':
        cmd_coverage(sys.argv[2])
    elif cmd == 'diff':
        cmd_diff(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())

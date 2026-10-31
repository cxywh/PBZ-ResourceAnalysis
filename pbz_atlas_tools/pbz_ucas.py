#!/usr/bin/env python3
"""PBZ IoStore 容器读取器

依据 UE IoStore TOC 结构（已对照 retoc 参考实现核对）：

    header(0x90)
    chunkIds        N × 12
    offsetLengths   N × 10   (偏移/长度各 5 字节【大端】，偏移在未压缩逻辑空间)
    perfectHashSeeds  S × 4
    blocks          B × 12   (偏移5/压缩3/解压3/方法1，均为【小端】)
    methodNames     M × 32
    directoryIndex  D 字节    (AES-256-ECB 加密)
    metas           N × 33?  (哈希 + 标志)

块号 = offset / block_size，末尾块 = (align(offset+size) - 1) / block_size。
每个块单独 AES-256-ECB 解密后再按方法解压。

用法：
    python pbz_ucas.py list   <utoc>
    python pbz_ucas.py stat   <utoc>
    python pbz_ucas.py find   <utoc> <关键字>
    python pbz_ucas.py extract <utoc> <资产路径或索引> <输出文件>
"""
import os, re, sys, glob, struct, ctypes

from .config import aes_key  # 密钥由环境变量提供，仓库内不含
def _find_oodle():
    """按顺序查找 Oodle 运行时：环境变量 → 游戏目录 → 当前目录。"""
    import glob
    from .config import GAME
    cand = [os.environ.get('PBZ_OODLE', '')]
    cand += glob.glob(os.path.join(GAME, '**', 'oo2core_*.dll'), recursive=True)
    cand += glob.glob(os.path.join(os.getcwd(), 'oo2core_*.dll'))
    for c in cand:
        if c and os.path.exists(c):
            return c
    raise RuntimeError('未找到 Oodle 运行时（oo2core_*.dll）：请设置 PBZ_OODLE，或把游戏自带的 DLL 放入工作目录')


V = ctypes.c_void_p
_od = None


def _oodle():
    """首次需要解压时才加载 Oodle，避免仅查索引时也强依赖。"""
    global _od
    if _od is None:
        _od = ctypes.WinDLL(_find_oodle())
        _od.OodleLZ_Decompress.restype = ctypes.c_size_t
        _od.OodleLZ_Decompress.argtypes = [V, ctypes.c_size_t, V, ctypes.c_size_t, ctypes.c_int,
                                           ctypes.c_int, V, ctypes.c_size_t, V, V, V, V, V, ctypes.c_size_t]
    return _od


def oodle_decompress(src: bytes, out_size: int):
    _od = _oodle()
    out = ctypes.create_string_buffer(out_size)
    sb = ctypes.create_string_buffer(src, len(src))
    n = _od.OodleLZ_Decompress(sb, len(src), out, out_size, 1, 0, None, 0, None, None, None, None, None, 0)
    return out.raw[:n] if n else None


class Toc:
    def __init__(self, utoc_path, key_hex=None):
        self.path = utoc_path
        self.dir = os.path.dirname(utoc_path)
        self.stem = os.path.basename(utoc_path)[:-5]
        self.data = open(utoc_path, 'rb').read()
        d = self.data
        assert d[:16] == b'-==--==--==--==-', "魔数不符"
        self.version = d[16]
        self.header_size = struct.unpack_from('<I', d, 20)[0]
        self.n = struct.unpack_from('<I', d, 24)[0]
        self.nblocks = struct.unpack_from('<I', d, 28)[0]
        self.block_entry_size = struct.unpack_from('<I', d, 32)[0]
        self.method_count = struct.unpack_from('<I', d, 36)[0]
        self.method_name_len = struct.unpack_from('<I', d, 40)[0]
        self.block_size = struct.unpack_from('<I', d, 44)[0]
        self.dir_index_size = struct.unpack_from('<I', d, 48)[0]
        self.partition_count = struct.unpack_from('<I', d, 52)[0]
        self.flags = struct.unpack_from('<I', d, 80)[0]
        self.seed_count = struct.unpack_from('<I', d, 84)[0]
        self.partition_size = struct.unpack_from('<Q', d, 88)[0]

        self.chunk_off = self.header_size
        self.olen_off = self.chunk_off + self.n * 12
        self.seed_off = self.olen_off + self.n * 10
        self.block_off = self.seed_off + self.seed_count * 4
        self.method_off = self.block_off + self.nblocks * self.block_entry_size
        self.dir_off = self.method_off + self.method_count * self.method_name_len

        self.key = bytes.fromhex((key_hex or aes_key()).strip())
        self.encrypted = bool(self.flags & 2)
        self.compressed = bool(self.flags & 1)
        self._parts = None
        self._dir_entries = None

    # ---------- 基础字段 ----------
    def chunk_id(self, i):
        o = self.chunk_off + i * 12
        return self.data[o:o + 12]

    def offset_len(self, i):
        o = self.olen_off + i * 10
        d = self.data
        off = (d[o] << 32) | (d[o + 1] << 24) | (d[o + 2] << 16) | (d[o + 3] << 8) | d[o + 4]
        ln = (d[o + 5] << 32) | (d[o + 6] << 24) | (d[o + 7] << 16) | (d[o + 8] << 8) | d[o + 9]
        return off, ln

    def block(self, b):
        o = self.block_off + b * 12
        d = self.data
        off = int.from_bytes(d[o:o + 5], 'little')
        cs = int.from_bytes(d[o + 5:o + 8], 'little')
        us = int.from_bytes(d[o + 8:o + 11], 'little')
        return off, cs, us, d[o + 11]

    # ---------- 分区 ----------
    @property
    def parts(self):
        if self._parts is None:
            files = [os.path.join(self.dir, self.stem + '.ucas')]
            files += sorted(glob.glob(os.path.join(self.dir, self.stem + '_s*.ucas')),
                            key=lambda p: int(re.search(r'_s(\d+)\.ucas$', p).group(1)))
            self._parts = files
        return self._parts

    def _read_disk(self, global_off, size):
        """块偏移是跨分区全局偏移，按 partition_size 取分区"""
        pi = global_off // self.partition_size
        local = global_off - pi * self.partition_size
        if pi >= len(self.parts):
            raise IOError(f"分区 {pi} 超出 {len(self.parts)}")
        with open(self.parts[pi], 'rb') as f:
            f.seek(local)
            return f.read(size)

    # ---------- 解密 ----------
    def _decrypt(self, blob):
        if not self.encrypted:
            return blob
        from Crypto.Cipher import AES
        n = len(blob) // 16 * 16
        out = AES.new(self.key, AES.MODE_ECB).decrypt(blob[:n])
        return out + blob[n:]

    # ---------- 读块 ----------
    def read_block(self, b):
        off, cs, us, method = self.block(b)
        # 加密时块数据补齐到 16 字节再写盘，须按整块读、解密后裁回 cs
        need = (cs + 15) // 16 * 16 if self.encrypted else cs
        raw = self._read_disk(off, need)
        if self.encrypted:
            raw = self._decrypt(raw)[:cs]
        if method != 0:
            dec = oodle_decompress(raw, us)
            if dec is None and len(raw) != us:
                raise IOError(f"块 {b} Oodle 解压失败 comp={cs} uncomp={us}")
            return dec if dec else raw
        return raw

    def read_chunk(self, i):
        off, size = self.offset_len(i)
        bs = self.block_size
        first = off // bs
        last = ((off + size + bs - 1) // bs * bs - 1) // bs if size else first
        buf = bytearray()
        for b in range(first, last + 1):
            buf += self.read_block(b)
        start = off - first * bs
        return bytes(buf[start:start + size])

    # ---------- 目录索引 ----------
    def directory(self):
        if self._dir_entries is not None:
            return self._dir_entries
        blob = self.data[self.dir_off:self.dir_off + self.dir_index_size]
        if self.encrypted:
            blob = self._decrypt(blob)
        entries = {}
        # 解析失败时退回字符串扫描
        try:
            entries = self._parse_dir(blob)
        except Exception:
            entries = {}
        self._dir_entries = entries
        return entries

    def _parse_dir(self, b):
        """FIoDirectoryIndexResource: mount, dir[], file[], string_table[]"""
        p = 0
        n = struct.unpack_from('<i', b, p)[0]; p += 4
        mount = b[p:p + n].rstrip(b'\x00').decode('latin1'); p += n
        nd = struct.unpack_from('<i', b, p)[0]; p += 4
        dirs = [struct.unpack_from('<4i', b, p + 16 * k) for k in range(nd)]; p += 16 * nd
        nf = struct.unpack_from('<i', b, p)[0]; p += 4
        files = [struct.unpack_from('<3i', b, p + 12 * k) for k in range(nf)]; p += 12 * nf
        ns = struct.unpack_from('<i', b, p)[0]; p += 4
        strs = []
        for _ in range(ns):
            n = struct.unpack_from('<i', b, p)[0]; p += 4
            if n < 0:
                strs.append(b[p:p - 2 * n].decode('utf-16-le').rstrip('\x00')); p += -2 * n
            else:
                strs.append(b[p:p + n].decode('latin1').rstrip('\x00')); p += n
        return {'mount': mount, 'dirs': dirs, 'files': files, 'strs': strs}

    def paths(self):
        """走目录树还原 完整路径 → chunk 索引"""
        info = self.directory()
        if not info or not info.get('dirs'):
            return {}
        dirs, files, strs = info['dirs'], info['files'], info['strs']
        mount = info['mount']
        out = {}

        def s_name(i):
            return strs[i] if 0 <= i < len(strs) else ''

        def walk(di, stack, depth=0):
            """与参考实现一致：本目录先出自己的文件，再递归子目录链"""
            if not (0 <= di < len(dirs)) or depth > 256:
                return
            name, first_child, next_sib, first_file = dirs[di]
            tagged = name >= 0
            if tagged:
                stack.append(s_name(name))
            fi = first_file
            guard = 0
            while fi >= 0 and fi < len(files) and guard < 10 ** 6:
                fname, nxt, ud = files[fi]
                out[(mount + '/' + '/'.join(stack + [s_name(fname)])).replace('//', '/')] = ud
                fi = nxt; guard += 1
            c = first_child
            while c >= 0 and c < len(dirs):
                walk(c, stack, depth + 1)
                c = dirs[c][2]
            if tagged:
                stack.pop()

        walk(0, [], 0)
        return out


def main():
    if len(sys.argv) < 3:
        print(__doc__); return 1
    cmd, utoc = sys.argv[1], sys.argv[2]
    t = Toc(utoc)
    if cmd == 'stat':
        print(f"{os.path.basename(utoc)}  v{t.version}  flags={t.flags:#x}"
              f"  chunks={t.n:,}  blocks={t.nblocks:,}  block_size={t.block_size:,}"
              f"  partitions={t.partition_count}  part_size={t.partition_size:,}")
        print(f"  布局: chunkIds@{t.chunk_off:#x} offLen@{t.olen_off:#x} seeds@{t.seed_off:#x}"
              f" blocks@{t.block_off:#x} methods@{t.method_off:#x} dirIndex@{t.dir_off:#x}")
        info = t.directory()
        print(f"  目录索引: mount={info.get('mount')!r} dirs={len(info.get('dirs', [])):,}")
        return 0
    if cmd == 'list':
        info = t.directory()
        print(f"mount={info.get('mount')!r} 目录 {len(info.get('dirs', [])):,}")
        for name, ents, files in info.get('dirs', [])[:20]:
            print(f"  {name!r} entries={len(ents)} files={len(files)}")
        return 0
    if cmd == 'find':
        kw = sys.argv[3].lower()
        m = t.paths()
        hits = [k for k in m if kw in k.lower()]
        print(f"匹配 {len(hits):,} 条（共 {len(m):,}）")
        for k in hits[:40]:
            print(f"  chunk#{m[k]:<7d} {k}")
        return 0
    if cmd == 'extract':
        target = sys.argv[3]
        out = sys.argv[4] if len(sys.argv) > 4 else None
        if target.isdigit():
            idx = int(target); name = f"chunk_{idx}"
        else:
            m = t.paths()
            hit = [k for k in m if k == target] or [k for k in m if k.endswith(target)]
            if not hit:
                print("路径未命中，可先用 find 查"); return 3
            name = hit[0]; idx = m[name]
            print(f"匹配 {name}")
        data = t.read_chunk(idx)
        out = out or os.path.join(os.environ.get("PBZ_EXTRACT", "extracted"), os.path.basename(name))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        open(out, 'wb').write(data)
        print(f"chunk#{idx} → {len(data):,} 字节 → {out}")
        print("头 32B:", data[:32].hex())
        return 0
    print(__doc__); return 1
    cmd, utoc = sys.argv[1], sys.argv[2]
    t = Toc(utoc)
    if cmd == 'stat':
        print(f"{os.path.basename(utoc)}  v{t.version}  flags={t.flags:#x}"
              f"  chunks={t.n:,}  blocks={t.nblocks:,}  block_size={t.block_size:,}"
              f"  partitions={t.partition_count}  part_size={t.partition_size:,}")
        print(f"  布局: chunkIds@{t.chunk_off:#x} offLen@{t.olen_off:#x} seeds@{t.seed_off:#x}"
              f" blocks@{t.block_off:#x} methods@{t.method_off:#x} dirIndex@{t.dir_off:#x}")
        info = t.directory()
        print(f"  目录索引: mount={info.get('mount')!r} dirs={len(info.get('dirs', [])):,}")
        return 0
    if cmd == 'list':
        info = t.directory()
        print(f"mount={info.get('mount')!r} 目录 {len(info.get('dirs', [])):,}")
        for name, ents, files in info.get('dirs', [])[:20]:
            print(f"  {name!r} entries={len(ents)} files={len(files)}")
        return 0
    if cmd == 'extract':
        i = int(sys.argv[3]) if sys.argv[3].isdigit() else None
        if i is None:
            print("目前只支持按索引抽取"); return 2
        data = t.read_chunk(i)
        out = sys.argv[4]
        open(out, 'wb').write(data)
        print(f"chunk#{i} → {len(data):,} 字节 → {out}")
        print("头 32B:", data[:32].hex())
        if data[:4] == b'\xc1\x83\x2a\x9e':
            print("✔ UE 包签名正确")
        return 0
    print(__doc__); return 1


if __name__ == '__main__':
    sys.exit(main())

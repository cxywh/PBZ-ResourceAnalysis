"""解析单个 Zen 包（IoStore chunk）的头部：名字表 / 导入表 / 导出表。

布局来自 retoc 源码（retoc/src/zen.rs）：
- FZenPackageSummary（52 字节，container_header_version > Initial）
- has_versioning_info != 0 时跟 FZenPackageVersioningInfo
- header_version >= SoftPackageReferencesOffset 时跟 cell_import/export_map_offset
- FNameMap：u32 num | u32 string_bytes | u64 hash_version | u64[num] hashes | i16[num] 长度 | 字符区
- import_map / export_map / export_bundle_entries 按 summary 里的偏移定位
"""
import struct
import sys

FEXPORT = 0x48
MNAME = 8


def name_batch(d, off):
    num, nbytes, hv = struct.unpack_from('<IIQ', d, off)
    p = off + 16
    hashes = d[p:p + num * 8]
    p += num * 8
    lens = struct.unpack_from(f'<{num}h', d, p)
    p += num * 2
    chars = d[p:p + nbytes]
    out = []
    cur = 0
    for i in range(num):
        ln = lens[i]
        if ln < 0:      # UTF-16
            ln = -ln - 32768
            out.append(chars[cur:cur + ln * 2].decode('utf-16-le', 'replace'))
            cur += ln * 2
        else:
            out.append(chars[cur:cur + ln].decode('latin-1'))
            cur += ln
    return out


def parse(path):
    d = open(path, 'rb').read()
    has_vi, header_size = struct.unpack_from('<II', d, 0)
    nidx, nnum = struct.unpack_from('<II', d, 8)
    flags, cooked = struct.unpack_from('<II', d, 0x10)
    pub_hash_off, imp_off, exp_off, bundle_off = struct.unpack_from('<iiii', d, 0x18)
    dep_hdr_off, dep_ent_off, impnames_off = struct.unpack_from('<iii', d, 0x28)
    cell_imp_off, cell_exp_off = struct.unpack_from('<ii', d, 0x34)
    print(f'header_size={header_size} cooked={cooked} flags={flags:#x} '
          f'imp={imp_off:#x} exp={exp_off:#x} bundle={bundle_off:#x} '
          f'dep_hdr={dep_hdr_off:#x} cell_imp={cell_imp_off:#x}')
    names = name_batch(d, 0x3c)
    print(f'名字表 {len(names)} 条，前 5: {names[:5]}')
    n_imp = (exp_off - imp_off) // 8
    n_exp = (cell_imp_off - exp_off) // FEXPORT
    print(f'导入 {n_imp} 条，导出 {n_exp} 条')
    exports = []
    for i in range(n_exp):
        o = exp_off + i * FEXPORT
        so, ss = struct.unpack_from('<QQ', d, o)
        on_idx, on_num = struct.unpack_from('<II', d, o + 16)
        obj_flags = struct.unpack_from('<I', d, o + 16 + 8 + 32 + 8)[0]
        exports.append((i, so, ss, on_idx, on_num, obj_flags))
        nm = names[on_idx] if on_idx < len(names) else f'<{on_idx}>'
        print(f'  导出[{i}] name={nm!r} num={on_num} flag={obj_flags:#x} '
              f'offset={so:#x} size={ss}')
    return d, names, exports


if __name__ == '__main__':
    parse(sys.argv[1]) if len(sys.argv) > 1 else print(__doc__)

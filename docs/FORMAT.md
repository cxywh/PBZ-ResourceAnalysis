# 格式笔记（实测）

以下结论来自对 `ProjectPBZ-Windows.utoc` 及其 chunk 的直接读取与逐字段验证，不含任何游戏内容。

## 1. IoStore TOC

文件以魔数 `-==--==--==--==-` 开头（16 字节），随后：

| 偏移 | 含义 |
|---|---|
| 0x10 | version（实测 8） |
| 0x14 | header_size（0x90） |
| 之后 | chunkIds / offsetLengths / hashSeeds / blocks / methodNames / directoryIndex |

关键点：

- `offsetLengths` 每条 10 字节，偏移与长度各占 5 字节，**大端**；偏移位于未压缩的逻辑空间。
- `blocks` 记录每个物理块的压缩方式与长度，压缩算法名在 `methodNames` 中（实测 `Oodle`）。
- `directoryIndex` 段整体加密（AES-ECB，密钥需自备），解密后是 `FIoDirectoryIndexResource`：mount + 目录表 + 文件表 + 字符串表。

## 2. Zen 包（IoStore 中的 `.uasset`）

UE5 的 cooked 包在 IoStore 里**没有** `C1832A9E` 头，结构为：

```
FZenPackageSummary
  u32 has_versioning_info        // 非 0 时紧跟 versioning info
  u32 header_size                // 头部总长，导出数据从这里开始
  FMappedName name               // u32 index + u32 number
  u32 package_flags
  u32 cooked_header_size
  i32 imported_public_export_hashes_offset
  i32 import_map_offset
  i32 export_map_offset
  i32 export_bundle_entries_offset
  i32 dependency_bundle_headers_offset
  i32 dependency_bundle_entries_offset
  i32 imported_package_names_offset
  （version 高时追加 cell_import_map_offset / cell_export_map_offset）
FNameMap                        // u32 num, u32 num_bytes, u64 hash_version(0xC1640000)
                                // u8[num*8] 哈希, i16[num] 长度(负值表示 UTF-16), 字符区
import map / export map / export bundle entries
```

- `FExportMapEntry` 定长 **0x48**：`i64 cooked_serial_offset`（相对 `header_size`）、`i64 cooked_serial_size`、`FMappedName object_name`、`u64 outer_index`、`u64 class_index` ……
- 导出数据 = `data[header_size : header_size + cooked_serial_size]`。

## 3. 贴图像素定位

对 UI 贴图实测：

- 像素数据在导出体内的起点多数为 **偏移 3**，不是尾部对齐。
- BC7 为 1 字节/像素，因此 `宽 × 高 == 数据长度`，尺寸可由字节数反推（实测命中 256/512/2048）。
- 起点不固定时，用 `pbz_texoff.py` 扫描 0–96 偏移，取「水平相邻像素平均差」最小者。
- 判据：真实彩色图标该分数约 8–11，噪点/白模遮罩 40+；遮罩类应改用 alpha 通道渲染剪影。

## 4. DataTable 行数据

- 行内 4 字节槽可为 FName 索引，需按容器/运行时的名字表解析。
- FName 索引存在下界：小于 0x2000 的多为引擎标识符（`None`、`ByteProperty`），需过滤，否则误判。
- 行宽不能取结构体的属性个数；用「同表行指针最小正间距」作为上界更可靠。
- 属性描述块（0x20 字节/条）中的 `a` / `b` 是**序列化体积**（`b = ceil(a/8)*8`），不是内存布局，不能用于累加计算偏移。

# PBZ-ResourceAnalysis

从 UE5 IoStore 容器里读取 DataTable 与 UI 贴图，生成「图片 + ID」图鉴，并对不同版本做数据 diff 的工具集。

以《Phantom Blade Zero》实测数据打磨，格式解析部分对同类 UE5 IoStore 游戏通用。

## 这个仓库不含什么

- **不含容器 AES 密钥**。密钥由使用者自行获取，通过环境变量注入。
- **不含任何游戏资产**：贴图、模型、DataTable 内容均不入库，全部由使用者在本地生成。
- **不含 Oodle 运行时**（`oo2core_*.dll` 属 RAD 专有组件），需从自己的游戏目录引用。

## 能力

| 模块 | 作用 |
|---|---|
| `pbz_ucas.py` | IoStore `.utoc` 索引解析、分块解密解压、按路径或 chunk 号取数据 |
| `pbz_zen.py` | Zen 包头部解析：名字表、导入表、导出表、导出体定位 |
| `pbz_tex.py` | 贴图解码：由字节数反推尺寸，BC7/BC6/BC5/BC3/BC1 → PNG |
| `pbz_atlas.py` | 表 → 图标资产 → PNG 流水线，输出自包含 HTML |
| `pbz_atlas2b.py` | 成品分类（彩色/剪影）、遮罩转剪影、拼图、打包 |
| `pbz_qc.py` | 量化质检：相邻像素差 + alpha 覆盖率，区分真实贴图与噪点遮罩 |
| `pbz_sheet.py` | 拼图总览（带中文名与 ID） |
| `pbz_diff.py` | 版本 diff：快照 → 表增删 / 行数变化 / 资产哈希 / 图鉴资产变化 |

## 安装

```bash
uv pip install -r requirements.txt
# 或
pip install -r requirements.txt
```

依赖：`pycryptodome`（容器解密）、`texture2ddecoder`（BC7 解码）、`pillow`、`numpy`。

## 配置

全部通过环境变量，仓库内没有任何硬编码路径：

```bash
export PBZ_GAME="D:/steam/steamapps/common/PBZ"   # 游戏安装目录（含 ProjectPBZ 的那一级）
export PBZ_OUT="./out"                             # 产物目录
export PBZ_KEY_FILE="./key.txt"                    # 密钥文件（一行十六进制）
# 或直接 export PBZ_AES_KEY="<hex>"
```

Oodle 解压需要把游戏自带的 `oo2core_*.dll` 放到 `PBZ_GAME` 下可被找到的位置，工具会按需加载。

## 用法

### 1. 取单个 chunk

```bash
python -m pbz_atlas_tools.pbz_ucas stat   "$PBZ_GAME/ProjectPBZ/Content/Paks/ProjectPBZ-Windows.utoc"
python -m pbz_atlas_tools.pbz_ucas find   "$PBZ_GAME/.../ProjectPBZ-Windows.utoc" "T_Icon_Weapon_WoodBlade"
python -m pbz_atlas_tools.pbz_ucas extract "$PBZ_GAME/.../ProjectPBZ-Windows.utoc" "T_Icon_Weapon_WoodBlade.uasset" out/x.uasset
python -m pbz_atlas_tools.pbz_zen out/x.uasset     # 打印 Zen 包头
python -m pbz_atlas_tools.pbz_tex out/x.uasset out/x.png
```

### 2. 生成图鉴

`pbz_atlas.py` 读取 `$PBZ_OUT/pbz_dt_values/*.csv`（每张 DataTable 的分列导出，列名形如 `+96[N]`，`[N]` 表示名字/路径列）与 `$PBZ_OUT/pbz_asset_files.txt`（一行一个资产路径）。

```bash
python -m pbz_atlas_tools.pbz_atlas all
python -m pbz_atlas_tools.pbz_atlas2b
```

产物：`$PBZ_OUT/atlas/{icons/,index.csv,atlas.html}`。

### 3. 版本 diff

```bash
python -m pbz_atlas_tools.pbz_diff snap v26266538
# 游戏更新后，重新导出数据，再打一次快照
python -m pbz_atlas_tools.pbz_diff snap v27xxxxxx
python -m pbz_atlas_tools.pbz_diff diff v26266538 v27xxxxxx
```

快照 JSON 结构（可自行生成，字段名保持即可）：

```json
{
  "build": "26266538",
  "runtime_tables": {"DT_WeaponData": 33},
  "container_tables": ["DT_WeaponData"],
  "assets_count": 296773,
  "assets_md5": "<md5 of sorted asset paths>",
  "atlas_assets": ["T_Icon_Weapon_WoodBlade"]
}
```

`coverage` 子命令比对同一快照内「容器侧表集合」与「运行时表集合」，用于发现只在容器里存在、运行时未加载的表。

## 数据从哪来

本工具只负责「容器 → 资产 → 图片」这一段。`pbz_dt_values/*.csv` 这类表数据由使用者在运行时读取 UObject 反射得到（属于各人自己的实现），或从其他合规来源取得。工具不包含该部分代码。

## 已知边界

- 贴图像素起点不固定，实测多数为导出体偏移 3 字节；`pbz_texoff.py` 可对单张图扫描最优起点。
- 只有形状遮罩的图标（RGB 为噪点、alpha 为轮廓）会被渲染成剪影，`pbz_qc.py` 的分数可用于区分。
- 密钥属于使用者自己的取证结果，不得随工具分发。

## 许可

MIT，见 LICENSE。使用前请确认所在地区法律与游戏用户协议；仅供个人研究与存档用途。

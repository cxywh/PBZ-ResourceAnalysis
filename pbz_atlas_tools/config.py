"""集中配置：所有路径与密钥都来自环境变量，仓库内不含任何密钥或游戏数据。

环境变量：
  PBZ_GAME     游戏安装目录（含 ProjectPBZ 的那一级），默认 D:/steam/steamapps/common/PBZ
  PBZ_OUT      产物输出根目录，默认 ./out
  PBZ_KEY_FILE 容器 AES 密钥文件（十六进制一行）；未设置时读取 PBZ_AES_KEY
  PBZ_AES_KEY  容器 AES 密钥（十六进制字符串）

密钥需由使用者自行获取，本仓库不提供、不分发。
"""
import os

GAME = os.environ.get('PBZ_GAME', 'D:/steam/steamapps/common/PBZ').replace('\\', '/')
OUT = os.path.abspath(os.environ.get('PBZ_OUT', 'out')).replace('\\', '/')

UTOC = f'{GAME}/ProjectPBZ/Content/Paks/ProjectPBZ-Windows.utoc'
ACF = os.path.join(os.path.dirname(os.path.dirname(GAME)), 'appmanifest_4115450.acf').replace('\\', '/')

EX = OUT
VAL = f'{OUT}/pbz_dt_values'
ATLAS = f'{OUT}/atlas'
ICONS = f'{ATLAS}/icons'
SNAPDIR = f'{OUT}/snapshots'
RUNTIME = f'{OUT}/pbz_dt_runtime/_index.csv'
ASSETS = os.environ.get('PBZ_ASSETS', f'{OUT}/pbz_asset_files.txt').replace('\\', '/')

DATA_ROOT = os.path.abspath(os.path.dirname(os.path.dirname(__file__))).replace('\\', '/')


def aes_key():
    """返回容器密钥的十六进制字符串；缺失时抛出可读错误。"""
    k = os.environ.get('PBZ_AES_KEY')
    if k:
        return k.strip()
    p = os.environ.get('PBZ_KEY_FILE')
    if p and os.path.exists(p):
        return open(p, encoding='utf-8').read().strip()
    raise RuntimeError('缺少容器密钥：请设置 PBZ_KEY_FILE 指向密钥文件，或注入 PBZ_AES_KEY 环境变量')

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
from mapping_definitions import MACRO_ROW_MAP

def test_macro_row_map_has_exact_coordinates() -> None:
    # ユーザー指摘事項: 「①段ボール」の「持込み」が3〜31行目、「引取り（自社/他社）」が33〜52行目
    # 単純な連番（r += 1）ではなく、絶対座標が設定されていることを検証する
    
    danball_mochikomi_indices = [
        idx for key, idx in MACRO_ROW_MAP.items() 
        if "①段ボール" in key and "持込み" in key
    ]
    
    # 最低でも1つは要素があること
    assert len(danball_mochikomi_indices) > 0
    
    # 持込みのインデックスが3〜31行目の範囲内に収まっていること
    for idx in danball_mochikomi_indices:
        assert 3 <= idx <= 31, f"連番バグ検知: 持込みのインデックス {idx} が3〜31の範囲外です"

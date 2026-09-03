import pandas as pd
from typing import List, Any
import logging
from mapping_definitions import YOKOMOCHI_KEYWORDS, MAJOR_CLIENTS, ITEM_TO_CATEGORY, MACRO_ROW_MAP, MICRO_ROW_MAP

logger = logging.getLogger(__name__)

def transform_raw_data(df: pd.DataFrame) -> pd.DataFrame:
    df["実重量"] = df["正味重量"].fillna(0) + df["調整重量"].fillna(0)
    df["横持フラグ"] = df["仕入先名"].apply(lambda x: any(kw in str(x) for kw in YOKOMOCHI_KEYWORDS) if pd.notna(x) else False)
    df["状態分類"] = df["品名"].apply(lambda x: "プレス品" if pd.notna(x) and "プレス" in str(x) else "バラ品")
    df["元品名"] = df["品名"]
    df["大品目分類"] = df["品名"].apply(lambda x: ITEM_TO_CATEGORY.get(str(x), "⑤その他") if pd.notna(x) else "⑤その他")

    def get_route(r: Any) -> str:
        if r.get("横持フラグ"): return "横持品"
        if r.get("状態分類") == "プレス品": return "-"
        tx = str(r.get("取引区分", ""))
        so = str(r.get("自社他社区分", ""))
        if tx == "持込": return "持込み"
        if tx == "引取":
            if so == "自社": return "自社回収"
            if so == "他社": return "他社回収"
        return "不明"

    df["経路分類"] = df.apply(get_route, axis=1)
    df["集計用仕入先名"] = df["仕入先名"].apply(lambda x: x if x in MAJOR_CLIENTS else "そのた")
    return df

def build_macro_report(df: pd.DataFrame) -> List[List[Any]]:
    """「8-5計」 346行 x 16列 の2次元配列を生成"""
    grid: List[List[Any]] = [["" for _ in range(16)] for _ in range(346)]
    
    for _, row in df.iterrows():
        cat = row.get("大品目分類", "")
        route = row.get("経路分類", "")
        supplier = row.get("集計用仕入先名", "")
        weight = row.get("実重量", 0.0)
        
        key = f"横持品_{supplier}" if route == "横持品" else f"{cat}_{route}_{supplier}"
        row_idx = MACRO_ROW_MAP.get(key)
        
        if row_idx is not None:
            grid[row_idx][0] = supplier
            grid[row_idx][1] = row.get("元品名", "") if cat == "⑤その他" else ""
            
            # C列(当月)としてインデックス2に加算
            current_val = grid[row_idx][2]
            grid[row_idx][2] = (float(current_val) if current_val else 0.0) + float(weight)

    return grid

def build_micro_report(df: pd.DataFrame) -> List[List[Any]]:
    """「8-5」 875行 x 41列 の2次元配列を生成"""
    grid: List[List[Any]] = [["" for _ in range(41)] for _ in range(875)]
    
    for _, row in df.iterrows():
        supplier = row.get("集計用仕入先名", "")
        weight = row.get("実重量", 0.0)
        
        row_idx = MICRO_ROW_MAP.get(supplier)
        if row_idx is not None:
            # F列(インデックス5)に1日のデータ
            current_val = grid[row_idx][5]
            grid[row_idx][5] = (float(current_val) if current_val else 0.0) + float(weight)
            
            # AK列(インデックス36)に月間合計
            current_total = grid[row_idx][36]
            grid[row_idx][36] = (float(current_total) if current_total else 0.0) + float(weight)
            
    return grid

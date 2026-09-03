import pandas as pd
from typing import List, Any
import logging

logger = logging.getLogger(__name__)

YOKOMOCHI_KEYWORDS = ["富士", "浜松", "御殿場", "(横持)"]
MAJOR_CLIENTS = {
    "タチオカ商会", "青木商店", "IWD", "カナキン", "浅見運輸倉庫", "ダイコー商事",
    "旭満", "対馬商店", "アオイ", "湘南（上田商店）", "湘南リユース", "中央カンセー",
    "サンクリーン", "神奈中商事", "関東ダイレクトサービス", "共栄商社", "ティーエスエンバイロ",
    "厚木市資源再生センター", "厚木資源再生センター", "アイダスト", "クリーンサービス",
    "アクト・エア", "北湘ヴィークル", "セクメット", "清水商店", "旭商会", "未竜運輸",
    "坂田亮作商店", "JSRネット（富士通関連）", "ｸﾘｰﾝｻｰﾋﾞｽ（ﾀｷﾛﾝほか）", "山櫻",
    "コトブキパック", "ニッポンロジ株式会社", "ﾎﾟｼﾞﾃｨﾌﾞ（富士ﾛｼﾞ関連）", "DSP（ピアノ運送ほか）",
    "DSP", "田丸（エスポットほか）", "田丸", "アークル", "アート引越センター", "アオイ（富士電線）",
    "ナカダイ（東京冷機ほか）", "丸紅（不二家）", "高山常温一括センター", "高山一括センター",
    "大本紙料（クリエイトほか）", "大本紙料", "共栄商社（ストリックスほか）", "TS環境リサイクル",
    "大創産業 神奈川RDC", "紙商", "中村伸行", "毎日新聞秦野", "平塚環興", "キョウセイ環境",
    "三星産業", "ｴｺｻﾎﾟｰﾄ（ﾊﾟﾙｼｽﾃﾑ）", "湘南リンテック加工", "東部サービスセンター",
    "リンテック", "三善製紙", "ユーネット", "吉田印刷", "パスコ"
}

ITEM_TO_CATEGORY = {
    "段ボール": "①段ボール", "新聞": "②新聞", "雑誌": "③雑誌", "PETボトル": "④プラ類", "その他": "⑤その他"
}

MACRO_ROW_MAP = {
    "①段ボール_自社回収_青木商店": 2,
    "⑤その他_持込み_そのた": 168,
    "横持品_富士営業所(横持)": 171
}

MICRO_ROW_MAP = {
    "青木商店": 5,
    "そのた": 870
}

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

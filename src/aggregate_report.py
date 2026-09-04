import pandas as pd
from typing import List, Any
import logging
from mapping_definitions import MACRO_ROW_MAP, MICRO_ROW_MAP

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


def transform_raw_data(df: pd.DataFrame) -> pd.DataFrame:
    df["実重量"] = df["正味重量"].fillna(0) + df["調整重量"].fillna(0)
    df["横持フラグ"] = df["仕入先名"].apply(lambda x: any(kw in str(x) for kw in YOKOMOCHI_KEYWORDS) if pd.notna(x) else False)
    
    def classify_route(row):
        item_name = str(row.get("品名", ""))
        supplier = str(row.get("仕入先名", ""))
        
        if "プレス" in item_name:
            return "プレス品"
            
        route_val = str(row.get("経路", ""))
        if "持込" in route_val:
            return "持込み"
        if "自社" in route_val:
            return "自社回収"
        if "他社" in route_val:
            return "他社回収"
        
        # default logic
        if "引取" in route_val:
            return "自社回収"
            
        return "持込み"
        
    df["経路分類"] = df.apply(classify_route, axis=1)
    
    def map_category(item_name):
        for k, v in ITEM_TO_CATEGORY.items():
            if k in str(item_name):
                return v
        return "⑤その他"
        
    df["大品目分類"] = df["品名"].apply(map_category)
    
    def clean_supplier(x):
        s = str(x)
        for client in MAJOR_CLIENTS:
            if client in s:
                return client
        return "そのた"
        
    df["集計用仕入先名"] = df["仕入先名"].apply(clean_supplier)
    
    return df

def _find_macro_idx(supplier: str, cat: str, route: str, is_yokomochi: bool) -> int:
    if is_yokomochi:
        for k, v in MACRO_ROW_MAP.items():
            if "横持品" in k and supplier in k:
                return v
        return -1
        
    route_kw = ""
    if "持込" in route: route_kw = "持込"
    elif "自社" in route or "他社" in route or "引取" in route: route_kw = "引取"
    elif "プレス" in route: route_kw = "プレス"
    
    for k, v in MACRO_ROW_MAP.items():
        if supplier in k and cat in k and route_kw in k:
            return v
            
    # fallback without route_kw (e.g. for そのた)
    for k, v in MACRO_ROW_MAP.items():
        if supplier in k and cat in k:
            return v
            
    return -1

def build_macro_report(df: pd.DataFrame) -> List[List[Any]]:
    grid: List[List[Any]] = [["" for _ in range(16)] for _ in range(346)]
    
    for _, row in df.iterrows():
        supplier = row.get("集計用仕入先名", "")
        cat = row.get("大品目分類", "")
        route = row.get("経路分類", "")
        weight = row.get("実重量", 0.0)
        is_yokomochi = row.get("横持フラグ", False)
        
        idx = _find_macro_idx(supplier, cat, route, is_yokomochi)
        
        if idx != -1 and 1 <= idx <= 346:
            row_idx = idx - 1 # 0-indexed
            
            # Fill A, B columns
            if grid[row_idx][0] == "":
                grid[row_idx][0] = supplier
            
            if cat == "⑤その他" and not is_yokomochi:
                grid[row_idx][1] = str(row.get("品名", ""))
                
            current_val = grid[row_idx][2]
            if current_val == "":
                current_val = 0.0
            grid[row_idx][2] = float(current_val) + float(weight)
            
    return grid

def _find_micro_idx(supplier: str, cat: str, route: str) -> int:
    route_kw = ""
    if "持込" in route: route_kw = "持込"
    elif "自社" in route or "他社" in route or "引取" in route: route_kw = "引取"
    
    cat_clean = cat.replace("①", "").replace("②", "").replace("③", "").replace("④", "").replace("⑤", "")
    
    # Try exact match first
    for k, v in MICRO_ROW_MAP.items():
        if supplier in k and cat_clean in k and route_kw in k:
            return v
            
    # Try just supplier and route
    for k, v in MICRO_ROW_MAP.items():
        if supplier in k and route_kw in k:
            return v
            
    # Try just supplier
    for k, v in MICRO_ROW_MAP.items():
        if supplier in k:
            return v
            
    return -1

def build_micro_report(df: pd.DataFrame) -> List[List[Any]]:
    grid: List[List[Any]] = [["" for _ in range(41)] for _ in range(875)]
    
    for _, row in df.iterrows():
        supplier = row.get("集計用仕入先名", "")
        cat = row.get("大品目分類", "")
        route = row.get("経路分類", "")
        weight = row.get("実重量", 0.0)
        
        idx = _find_micro_idx(supplier, cat, route)
        if idx != -1 and 1 <= idx <= 875:
            row_idx = idx - 1
            
            # Day 1 is F (index 5)
            current_val = grid[row_idx][5]
            if current_val == "": current_val = 0.0
            grid[row_idx][5] = float(current_val) + float(weight)
            
            # Monthly total is AK (index 36)
            total_val = grid[row_idx][36]
            if total_val == "": total_val = 0.0
            grid[row_idx][36] = float(total_val) + float(weight)
            
    return grid

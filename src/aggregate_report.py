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


import unicodedata

def transform_raw_data(df: pd.DataFrame) -> pd.DataFrame:
    # 文字列カラムの表記揺れ（全角半角スペース除去、NFKC正規化）を処理
    for col in df.select_dtypes(include=['object', 'string']).columns:
        df[col] = df[col].apply(
            lambda x: unicodedata.normalize('NFKC', x).replace(" ", "").replace("　", "") if isinstance(x, str) else x
        )
        
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
    # 8-5計: C〜P列（14列分）。C=0, O=12(13ヶ月分), P=13(比較用)
    # 値が存在しないセルは None
    grid: List[List[Any]] = [[None for _ in range(14)] for _ in range(346)]
    
    if "transaction_date" in df.columns:
        df["_date"] = pd.to_datetime(df["transaction_date"], errors="coerce")
        df["_ym"] = df["_date"].dt.to_period("M")
    else:
        df["_date"] = pd.NaT
        df["_ym"] = pd.NaT
        
    unique_yms = sorted([ym for ym in df["_ym"].unique() if pd.notna(ym)])
    # 最新13ヶ月に制限
    if len(unique_yms) > 13:
        unique_yms = unique_yms[-13:]
        
    ym_to_col = {ym: i for i, ym in enumerate(unique_yms)}
    
    for _, row in df.iterrows():
        supplier = row.get("集計用仕入先名", "")
        cat = row.get("大品目分類", "")
        route = row.get("経路分類", "")
        weight = row.get("実重量", 0.0)
        is_yokomochi = row.get("横持フラグ", False)
        ym_val = row.get("_ym")
        
        idx = _find_macro_idx(supplier, cat, route, is_yokomochi)
        
        if idx != -1 and 1 <= idx <= 346:
            row_idx = idx - 1 # 0-indexed
            
            col_idx = ym_to_col.get(ym_val, -1) if pd.notna(ym_val) else -1
            if col_idx != -1:
                current_val = grid[row_idx][col_idx]
                if current_val is None: current_val = 0.0
                grid[row_idx][col_idx] = float(current_val) + float(weight)
            
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
    # 8-5: F〜AK列（32列分）。F=Day1(0), AJ=Day31(30), AK=Total(31)
    # 値が存在しないセルは None を設定し、gspread更新時に無視させる
    grid: List[List[Any]] = [[None for _ in range(32)] for _ in range(875)]
    
    if "transaction_date" in df.columns:
        df["_date"] = pd.to_datetime(df["transaction_date"], errors="coerce")
    else:
        df["_date"] = pd.NaT
        
    for _, row in df.iterrows():
        supplier = row.get("集計用仕入先名", "")
        cat = row.get("大品目分類", "")
        route = row.get("経路分類", "")
        weight = row.get("実重量", 0.0)
        date_val = row.get("_date")
        
        idx = _find_micro_idx(supplier, cat, route)
        if idx != -1 and 1 <= idx <= 875:
            row_idx = idx - 1
            
            # 日付から列インデックスを特定
            day_idx = -1
            if pd.notna(date_val):
                day = date_val.day
                if 1 <= day <= 31:
                    day_idx = day - 1
            
            # 日別実績の加算 (Day 1 = index 0)
            if day_idx != -1:
                current_val = grid[row_idx][day_idx]
                if current_val is None: current_val = 0.0
                grid[row_idx][day_idx] = float(current_val) + float(weight)
            
            # 行合計の加算 (AK = index 31)
            total_val = grid[row_idx][31]
            if total_val is None: total_val = 0.0
            grid[row_idx][31] = float(total_val) + float(weight)
            
    return grid

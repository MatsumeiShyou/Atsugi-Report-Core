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
    
    # MAJOR_CLIENTS を長い順にソートして、部分一致の誤爆を防ぐ
    sorted_clients = sorted(list(MAJOR_CLIENTS), key=len, reverse=True)
    def clean_supplier(x):
        s = str(x)
        for client in sorted_clients:
            if client in s:
                return client
        return "そのた"
        
    df["集計用仕入先名"] = df["仕入先名"].apply(clean_supplier)
    
    return df

def build_macro_report(df: pd.DataFrame) -> List[List[Any]]:
    # 8-5計: A〜P列（16列分）。A=階層見出し, B=補足, C(2)〜O(14)=月別, P(15)=合計
    grid: List[List[Any]] = []
    
    if "transaction_date" in df.columns:
        df["_date"] = pd.to_datetime(df["transaction_date"], errors="coerce")
        df["_ym"] = df["_date"].dt.to_period("M")
    else:
        df["_date"] = pd.NaT
        df["_ym"] = pd.NaT
        
    unique_yms = sorted([ym for ym in df["_ym"].unique() if pd.notna(ym)])
    if len(unique_yms) > 13:
        unique_yms = unique_yms[-13:]
        
    ym_to_col = {ym: (i + 2) for i, ym in enumerate(unique_yms)}
    
    # 見出し行を追加
    top_header = [None] * 16
    for ym, col_idx in ym_to_col.items():
        top_header[col_idx] = str(ym)
    top_header[15] = "合計"
    grid.append(top_header)
    
    categories = sorted(df["大品目分類"].dropna().unique())
    
    for cat in categories:
        cat_df = df[df["大品目分類"] == cat]
        routes = sorted(cat_df["経路分類"].dropna().unique())
        
        for route in routes:
            route_df = cat_df[cat_df["経路分類"] == route]
            
            # 見出し行 (Category - Route)
            header = [None] * 16
            header[0] = f"{cat} - {route}"
            grid.append(header)
            
            route_totals = [0.0] * 14 # 13 months + total
            
            suppliers = sorted(route_df["集計用仕入先名"].dropna().unique())
            for supplier in suppliers:
                supp_df = route_df[route_df["集計用仕入先名"] == supplier]
                row_data = [None] * 16
                
                row_data[0] = supplier
                raw_item = str(supp_df.iloc[0].get("品名", ""))
                row_data[1] = raw_item if raw_item else cat
                
                ym_sums = supp_df.groupby("_ym")["実重量"].sum()
                row_total = 0.0
                for ym, weight in ym_sums.items():
                    if ym in ym_to_col:
                        c_idx = ym_to_col[ym]
                        row_data[c_idx] = float(weight)
                        row_total += float(weight)
                        route_totals[c_idx - 2] += float(weight)
                
                row_data[15] = row_total
                route_totals[13] += row_total
                grid.append(row_data)
                
            # 小計行
            subtotal = [None] * 16
            subtotal[0] = f"{route} 合計"
            for i in range(13):
                if route_totals[i] > 0:
                    subtotal[i + 2] = route_totals[i]
            subtotal[15] = route_totals[13]
            grid.append(subtotal)
            
            grid.append([None] * 16) # 空行
            
    return grid

def build_micro_report(df: pd.DataFrame) -> List[List[Any]]:
    # 8-5: A〜AK列（37列分）。A~E(0~4)は属性テキスト、F(5)=Day1, AJ(35)=Day31, AK(36)=Total
    grid: List[List[Any]] = []
    
    if "transaction_date" in df.columns:
        df["_date"] = pd.to_datetime(df["transaction_date"], errors="coerce")
        df["_day"] = df["_date"].dt.day
    else:
        df["_date"] = pd.NaT
        df["_day"] = pd.NaT
        
    categories = sorted(df["大品目分類"].dropna().unique())
    
    for cat in categories:
        cat_df = df[df["大品目分類"] == cat]
        routes = sorted(cat_df["経路分類"].dropna().unique())
        
        for route in routes:
            route_df = cat_df[cat_df["経路分類"] == route]
            
            # 見出し行 (Category - Route)
            header = [None] * 37
            header[1] = f"{cat} - {route}"
            grid.append(header)
            
            route_totals = [0.0] * 32
            
            suppliers = sorted(route_df["集計用仕入先名"].dropna().unique())
            for supplier in suppliers:
                supp_df = route_df[route_df["集計用仕入先名"] == supplier]
                row_data = [None] * 37
                
                first = supp_df.iloc[0]
                row_data[0] = first.get("管理会社", "")
                row_data[1] = supplier
                row_data[2] = first.get("運搬業者", "")
                raw_item = str(first.get("品名", ""))
                row_data[3] = raw_item if raw_item else cat
                row_data[4] = route
                
                day_sums = supp_df.groupby("_day")["実重量"].sum()
                row_total = 0.0
                for day, weight in day_sums.items():
                    if pd.notna(day) and 1 <= day <= 31:
                        c_idx = int(day) + 4
                        row_data[c_idx] = float(weight)
                        row_total += float(weight)
                        route_totals[int(day) - 1] += float(weight)
                
                row_data[36] = row_total
                route_totals[31] += row_total
                grid.append(row_data)
                
            # 小計行
            subtotal = [None] * 37
            subtotal[1] = f"{route} 合計"
            for d in range(31):
                if route_totals[d] > 0:
                    subtotal[d + 5] = route_totals[d]
            subtotal[36] = route_totals[31]
            grid.append(subtotal)
            
            grid.append([None] * 37) # 空行
            
    return grid

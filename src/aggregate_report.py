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

MASTER_HIERARCHY = [
    {
        "cat_id": "①段ボール", "cat_disp": "段ボール",
        "routes": [
            {"route_id": "1.持込み・バラ", "route_match": ["持込み"], "route_disp": "持込"},
            {"route_id": "2.引取り・バラ", "route_match": ["自社回収", "他社回収"], "route_disp": "自社回収"},
            {"route_id": "3.段ボール・プレス", "route_match": ["プレス品"], "route_disp": "プレス品"}
        ]
    },
    {
        "cat_id": "②新聞", "cat_disp": "新聞",
        "routes": [
            {"route_id": "1.持込み・バラ", "route_match": ["持込み"], "route_disp": "持込"},
            {"route_id": "2.引取り・バラ", "route_match": ["自社回収", "他社回収"], "route_disp": "自社回収"},
            {"route_id": "3.新聞・プレス", "route_match": ["プレス品"], "route_disp": "プレス品"}
        ]
    },
    {
        "cat_id": "③雑誌", "cat_disp": "雑誌",
        "routes": [
            {"route_id": "1.持込み・バラ", "route_match": ["持込み"], "route_disp": "持込"},
            {"route_id": "2.引取り・バラ", "route_match": ["自社回収", "他社回収"], "route_disp": "自社回収"},
            {"route_id": "3.雑誌・プレス", "route_match": ["プレス品"], "route_disp": "プレス品"}
        ]
    },
    {
        "cat_id": "④プラ類", "cat_disp": "プラ類",
        "routes": [
            {"route_id": "1.持込み・バラ", "route_match": ["持込み"], "route_disp": "持込"},
            {"route_id": "2.引取り・バラ", "route_match": ["自社回収", "他社回収"], "route_disp": "自社回収"}
        ]
    },
    {
        "cat_id": "⑤その他", "cat_disp": "その他",
        "routes": [
            {"route_id": "1.持込み・バラ", "route_match": ["持込み"], "route_disp": "持込"},
            {"route_id": "2.引取り・バラ", "route_match": ["自社回収", "他社回収"], "route_disp": "自社回収"}
        ]
    },
    {
        "cat_id": "＜参考＞事業所間横持ち", "cat_disp": "＜出荷＞",
        "routes": [
            {"route_id": "事業所間横持", "route_match": ["横持"], "route_disp": "自社回収"}
        ]
    }
]

import datetime

def format_num(val: float) -> str:
    if val == 0:
        return "0"
    return f"{int(val):,}"

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
    
    for cat_info in MASTER_HIERARCHY:
        cat_id = cat_info["cat_id"]
        cat_disp = cat_info["cat_disp"]
        
        # 大分類見出し
        grid.append([cat_id] + [None] * 15)
        
        for route_info in cat_info["routes"]:
            route_id = route_info["route_id"]
            route_match_list = route_info["route_match"]
            
            if cat_id == "＜参考＞事業所間横持ち":
                route_df = df[df["横持フラグ"] == True].copy()
            else:
                route_df = df[(df["大品目分類"] == cat_id) & (df["経路分類"].isin(route_match_list)) & (df["横持フラグ"] == False)].copy()
            
            # 区分見出し
            grid.append(["", route_id] + [None] * 14)
            
            route_totals = [0.0] * 14 # 13 months + total
            
            if not route_df.empty:
                suppliers = sorted(route_df["集計用仕入先名"].dropna().unique())
                for supplier in suppliers:
                    supp_df = route_df[route_df["集計用仕入先名"] == supplier]
                    row_data = [None] * 16
                    row_data[0] = ""
                    row_data[1] = supplier
                    
                    ym_sums = supp_df.groupby("_ym")["実重量"].sum()
                    row_total = 0.0
                    for ym, weight in ym_sums.items():
                        if ym in ym_to_col:
                            c_idx = ym_to_col[ym]
                            row_data[c_idx] = format_num(float(weight))
                            row_total += float(weight)
                            route_totals[c_idx - 2] += float(weight)
                    
                    row_data[15] = format_num(row_total)
                    route_totals[13] += row_total
                    grid.append(row_data)
                    
            # 小計行
            subtotal = [None] * 16
            subtotal[0] = ""
            subtotal[1] = f"{route_id.split('.')[-1]}合計" if "." in route_id else f"{route_id}合計"
            for i in range(13):
                if route_totals[i] > 0:
                    subtotal[i + 2] = format_num(route_totals[i])
            subtotal[15] = format_num(route_totals[13])
            grid.append(subtotal)
            
        grid.append([None] * 16) # 空行
            
    return grid

def build_micro_report(df: pd.DataFrame) -> List[List[Any]]:
    grid: List[List[Any]] = []
    
    if "transaction_date" in df.columns:
        df["_date"] = pd.to_datetime(df["transaction_date"], errors="coerce")
        df["_day"] = df["_date"].dt.day
    else:
        df["_date"] = pd.NaT
        df["_day"] = pd.NaT
        
    valid_dates = df["_date"].dropna()
    year, month = 2026, 5
    if not valid_dates.empty:
        mode_date = valid_dates.dt.to_period("M").mode()
        if not mode_date.empty:
            year, month = mode_date.iloc[0].year, mode_date.iloc[0].month
            
    # Top Header 行 1
    row0 = [None] * 41
    row0[3] = f"{month}月"
    grid.append(row0)
    
    # Top Header 行 2
    row1 = [None] * 41
    row1[0] = "管理会社"
    row1[1] = "客先名称"
    row1[2] = "運搬業者"
    row1[3] = "品名"
    
    weekdays = ["月", "火", "水", "木", "金", "土", "日"]
    for d in range(1, 32):
        try:
            dt = datetime.date(year, month, d)
            wd = weekdays[dt.weekday()]
            day_str = f"{d}({wd})"
        except ValueError:
            day_str = f"{d}()"
        row1[4 + d] = day_str
    row1[36] = "合計"
    
    row1[38] = "カテゴリ・業者名"
    row1[39] = "品名等"
    row1[40] = "当月合計"
    grid.append(row1)
    
    right_side_data = []
    total_all = 0.0
    
    for cat_info in MASTER_HIERARCHY:
        cat_id = cat_info["cat_id"]
        cat_disp = cat_info["cat_disp"]
        
        right_side_data.append([cat_id, "", ""])
        cat_total = 0.0
        
        for route_info in cat_info["routes"]:
            route_id = route_info["route_id"]
            route_match_list = route_info["route_match"]
            route_disp = route_info["route_disp"]
            
            if cat_id == "＜参考＞事業所間横持ち":
                route_df = df[df["横持フラグ"] == True].copy()
            else:
                route_df = df[(df["大品目分類"] == cat_id) & (df["経路分類"].isin(route_match_list)) & (df["横持フラグ"] == False)].copy()
                
            h_row = [None] * 41
            h_row[0] = f"{cat_disp}-{route_disp}"
            grid.append(h_row)
            
            right_side_idx = len(right_side_data)
            right_side_data.append(["", route_id, ""])
            
            route_totals = [0.0] * 32
            
            if not route_df.empty:
                suppliers = sorted(route_df["集計用仕入先名"].dropna().unique())
                for supplier in suppliers:
                    supp_df = route_df[route_df["集計用仕入先名"] == supplier]
                    r_data = [None] * 41
                    
                    first = supp_df.iloc[0]
                    r_data[1] = supplier
                    r_data[2] = first.get("運搬業者", "")
                    raw_item = str(first.get("品名", ""))
                    r_data[3] = raw_item if raw_item else cat_disp
                    r_data[4] = route_disp
                    
                    day_sums = supp_df.groupby("_day")["実重量"].sum()
                    row_total = 0.0
                    for day, weight in day_sums.items():
                        if pd.notna(day) and 1 <= day <= 31:
                            c_idx = int(day) + 4
                            r_data[c_idx] = format_num(float(weight))
                            row_total += float(weight)
                            route_totals[int(day) - 1] += float(weight)
                    
                    r_data[36] = format_num(row_total)
                    route_totals[31] += row_total
                    grid.append(r_data)
                    
                    right_side_data.append(["", supplier, format_num(row_total)])
            
            # 小計
            sub_row = [None] * 41
            sub_row_title = f"{route_id.split('.')[-1]}合計" if "." in route_id else f"{route_id}合計"
            sub_row[1] = sub_row_title
            for d in range(31):
                if route_totals[d] > 0:
                    sub_row[d + 5] = format_num(route_totals[d])
            sub_row[36] = format_num(route_totals[31])
            grid.append(sub_row)
            
            # 常に右側の行ヘッダに合計を出す
            right_side_data[right_side_idx][2] = format_num(route_totals[31])
            right_side_data.append(["", sub_row_title, format_num(route_totals[31])])
            
            cat_total += route_totals[31]
            
        cat_total_row = [None] * 41
        cat_total_row[1] = f"{cat_disp}合計"
        cat_total_row[36] = format_num(cat_total)
        grid.append(cat_total_row)
        
        total_all += cat_total
        
        right_side_data.append(["", "", ""])
        grid.append([None] * 41)
        
    all_total_row = [None] * 41
    all_total_row[1] = "入荷合計"
    all_total_row[36] = format_num(total_all)
    grid.append(all_total_row)
    
    # 右側データを合成
    for i, r_data in enumerate(right_side_data):
        target_r = i + 2
        if target_r >= len(grid):
            grid.append([None] * 41)
        grid[target_r][38] = r_data[0]
        grid[target_r][39] = r_data[1]
        grid[target_r][40] = r_data[2]
        
    return grid

import pandas as pd
from typing import List, Any
import logging
import unicodedata
import datetime

logger = logging.getLogger(__name__)

YOKOMOCHI_KEYWORDS = ["富士", "浜松", "御殿場", "(横持)"]

ITEM_TO_CATEGORY = {
    "段ボール": "①段ボール", "新聞": "②新聞", "雑誌": "③雑誌", "PETボトル": "④プラ類", "その他": "⑤その他"
}

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
        inout = str(row.get("自社他社区分", ""))
        customer = str(row.get("得意先名", ""))
        transaction_type = str(row.get("取引区分", ""))
        
        # 出荷データの判定（得意先名が存在するなら出荷）
        if pd.notna(row.get("得意先名")) and customer.strip() not in ["", "None", "nan"]:
            if "輸出" in customer or "輸出" in str(row.get("備考", "")):
                return "輸出"
            return "国内"

        if "プレス" in item_name:
            return "プレス品"
            
        if "持込" in transaction_type:
            return "持込み"
            
        if "自社" in inout:
            return "自社回収"
        if "他社" in inout:
            return "他社回収"
            
        return "持込み"
        
    df["経路分類"] = df.apply(classify_route, axis=1)
    
    def map_category(item_name):
        for k, v in ITEM_TO_CATEGORY.items():
            if k in str(item_name):
                return v
        return "⑤その他"
        
    df["大品目分類"] = df["品名"].apply(map_category)
    
    # 支払先名（管理会社）、仕入先名（客先名称）、運送店名（運搬業者）の欠損値を空文字に
    df["支払先名"] = df.get("支払先名", pd.Series([None]*len(df))).fillna("")
    df["仕入先名"] = df.get("仕入先名", pd.Series([None]*len(df))).fillna("")
    df["運送店名"] = df.get("運送店名", pd.Series([None]*len(df))).fillna("")
    df["得意先名"] = df.get("得意先名", pd.Series([None]*len(df))).fillna("")
    
    return df

MASTER_HIERARCHY = [
    {
        "cat_id": "①段ボール", "cat_disp": "段ボール",
        "routes": [
            {"route_id": "1.持込み・バラ", "route_match": ["持込み"], "route_disp": "持込"},
            {"route_id": "2.引取り・バラ(自社)", "route_match": ["自社回収"], "route_disp": "自社回収"},
            {"route_id": "3.引取り・バラ(他社)", "route_match": ["他社回収"], "route_disp": "他社回収"},
            {"route_id": "4.段ボール・プレス", "route_match": ["プレス品"], "route_disp": "プレス品"}
        ]
    },
    {
        "cat_id": "②新聞", "cat_disp": "新聞",
        "routes": [
            {"route_id": "1.持込み・バラ", "route_match": ["持込み"], "route_disp": "持込"},
            {"route_id": "2.引取り・バラ(自社)", "route_match": ["自社回収"], "route_disp": "自社回収"},
            {"route_id": "3.引取り・バラ(他社)", "route_match": ["他社回収"], "route_disp": "他社回収"},
            {"route_id": "4.新聞・プレス", "route_match": ["プレス品"], "route_disp": "プレス品"}
        ]
    },
    {
        "cat_id": "③雑誌", "cat_disp": "雑誌",
        "routes": [
            {"route_id": "1.持込み・バラ", "route_match": ["持込み"], "route_disp": "持込"},
            {"route_id": "2.引取り・バラ(自社)", "route_match": ["自社回収"], "route_disp": "自社回収"},
            {"route_id": "3.引取り・バラ(他社)", "route_match": ["他社回収"], "route_disp": "他社回収"},
            {"route_id": "4.雑誌・プレス", "route_match": ["プレス品"], "route_disp": "プレス品"}
        ]
    },
    {
        "cat_id": "④プラ類", "cat_disp": "プラ類",
        "routes": [
            {"route_id": "1.持込み・バラ", "route_match": ["持込み"], "route_disp": "持込"},
            {"route_id": "2.引取り・バラ(自社)", "route_match": ["自社回収"], "route_disp": "自社回収"},
            {"route_id": "3.引取り・バラ(他社)", "route_match": ["他社回収"], "route_disp": "他社回収"}
        ]
    },
    {
        "cat_id": "⑤その他", "cat_disp": "その他",
        "routes": [
            {"route_id": "1.持込み・バラ", "route_match": ["持込み"], "route_disp": "持込"},
            {"route_id": "2.引取り・バラ(自社)", "route_match": ["自社回収"], "route_disp": "自社回収"},
            {"route_id": "3.引取り・バラ(他社)", "route_match": ["他社回収"], "route_disp": "他社回収"}
        ]
    },
    {
        "cat_id": "＜参考＞事業所間横持ち", "cat_disp": "事業所間横持ち",
        "routes": [
            {"route_id": "事業所間横持", "route_match": ["横持"], "route_disp": "自社回収"}
        ]
    }
]

SHIPPING_HIERARCHY = [
    {
        "cat_id": "①段ボール", "cat_disp": "段ボール",
        "routes": [
            {"route_id": "1.輸出", "route_match": ["輸出"], "route_disp": "輸出"},
            {"route_id": "2.国内", "route_match": ["国内"], "route_disp": "国内"}
        ]
    },
    {
        "cat_id": "②新聞", "cat_disp": "新聞",
        "routes": [
            {"route_id": "1.輸出", "route_match": ["輸出"], "route_disp": "輸出"},
            {"route_id": "2.国内", "route_match": ["国内"], "route_disp": "国内"}
        ]
    },
    {
        "cat_id": "③雑誌", "cat_disp": "雑誌",
        "routes": [
            {"route_id": "1.輸出", "route_match": ["輸出"], "route_disp": "輸出"},
            {"route_id": "2.国内", "route_match": ["国内"], "route_disp": "国内"}
        ]
    },
    {
        "cat_id": "④プラ類", "cat_disp": "プラ類",
        "routes": [
            {"route_id": "1.輸出", "route_match": ["輸出"], "route_disp": "輸出"},
            {"route_id": "2.国内", "route_match": ["国内"], "route_disp": "国内"}
        ]
    },
    {
        "cat_id": "⑤その他", "cat_disp": "その他",
        "routes": [
            {"route_id": "1.輸出", "route_match": ["輸出"], "route_disp": "輸出"},
            {"route_id": "2.国内", "route_match": ["国内"], "route_disp": "国内"}
        ]
    }
]


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
                suppliers = sorted(route_df["仕入先名"].dropna().unique())
                for supplier in suppliers:
                    supp_df = route_df[route_df["仕入先名"] == supplier]
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
    row1[4] = ""
    
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
    
    # === 入荷セクション ===
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
                # groupby 細分化キー
                group_keys = ["支払先名", "仕入先名", "運送店名", "品名"]
                grouped = route_df.groupby(group_keys)
                
                # keyごとにソートして出力
                for keys, supp_df in sorted(grouped):
                    r_data = [None] * 41
                    r_data[0] = keys[0] # 管理会社
                    r_data[1] = keys[1] # 客先名称
                    r_data[2] = keys[2] # 運搬業者
                    r_data[3] = keys[3] # 品名
                    r_data[4] = route_disp
                    
                    row_total = 0.0
                    day_sums = supp_df.groupby("_day")["実重量"].sum()
                    for d, weight in day_sums.items():
                        if pd.notna(d) and 1 <= int(d) <= 31:
                            r_data[4 + int(d)] = format_num(float(weight))
                            row_total += float(weight)
                            route_totals[int(d)] += float(weight)
                            
                    r_data[36] = format_num(row_total)
                    route_totals[0] += row_total
                    grid.append(r_data)
                    
                    # 業者名を出力（右側集計枠用）
                    disp_supplier = keys[1] if keys[1] else keys[0]
                    right_side_data.append(["", disp_supplier, format_num(row_total)])
                    
            # 小計行
            subtotal = [None] * 41
            subtotal_label = f"{route_id.split('.')[-1]}合計" if "." in route_id else f"{route_id}合計"
            subtotal[4] = subtotal_label
            for d in range(1, 32):
                if route_totals[d] > 0:
                    subtotal[4 + d] = format_num(route_totals[d])
            subtotal[36] = format_num(route_totals[0])
            grid.append(subtotal)
            
            cat_total += route_totals[0]
            right_side_data[right_side_idx][2] = format_num(route_totals[0])
            
        # 大分類合計行
        cat_total_row = [None] * 41
        cat_total_row[4] = f"{cat_disp}合計"
        cat_total_row[36] = format_num(cat_total)
        grid.append(cat_total_row)
        
        # 空行
        grid.append([None] * 41)
        
        total_all += cat_total
        
    # 入荷総合計行
    grand_total = [None] * 41
    grand_total[4] = "入荷総合計"
    grand_total[36] = format_num(total_all)
    grid.append(grand_total)
    grid.append([None] * 41)
    
    # === 出荷セクション ===
    grid.append(["＜出荷＞"] + [None]*40)
    
    shipping_total_all = 0.0
    for cat_info in SHIPPING_HIERARCHY:
        cat_id = cat_info["cat_id"]
        cat_disp = cat_info["cat_disp"]
        cat_total = 0.0
        
        has_cat_header = False
        
        for route_info in cat_info["routes"]:
            route_id = route_info["route_id"]
            route_match_list = route_info["route_match"]
            
            # 出荷データ抽出条件
            route_df = df[(df["大品目分類"] == cat_id) & (df["経路分類"].isin(route_match_list))].copy()
            if route_df.empty:
                continue
                
            if not has_cat_header:
                grid.append(["", cat_id] + [None]*39)
                has_cat_header = True
                
            grid.append(["", route_id] + [None]*39)
            
            route_totals = [0.0] * 32
            
            group_keys = ["得意先名", "品名"]
            grouped = route_df.groupby(group_keys)
            
            for keys, supp_df in sorted(grouped):
                r_data = [None] * 41
                r_data[1] = keys[0] # 得意先名
                r_data[3] = keys[1] # 品名
                
                row_total = 0.0
                day_sums = supp_df.groupby("_day")["実重量"].sum()
                for d, weight in day_sums.items():
                    if pd.notna(d) and 1 <= int(d) <= 31:
                        r_data[4 + int(d)] = format_num(float(weight))
                        row_total += float(weight)
                        route_totals[int(d)] += float(weight)
                        
                r_data[36] = format_num(row_total)
                route_totals[0] += row_total
                grid.append(r_data)
                
            # 小計行 (輸出合計, 国内合計)
            subtotal = [None] * 41
            subtotal[1] = f"{route_id.split('.')[-1]}合計"
            for d in range(1, 32):
                if route_totals[d] > 0:
                    subtotal[4 + d] = format_num(route_totals[d])
            subtotal[36] = format_num(route_totals[0])
            grid.append(subtotal)
            grid.append([None] * 41)
            
            cat_total += route_totals[0]
            
        if cat_total > 0:
            cat_total_row = [None] * 41
            cat_total_row[1] = f"{cat_disp}出荷合計"
            cat_total_row[36] = format_num(cat_total)
            grid.append(cat_total_row)
            grid.append([None] * 41)
            shipping_total_all += cat_total
            
    # 出荷総合計行
    if shipping_total_all > 0:
        ship_grand_total = [None] * 41
        ship_grand_total[1] = "出荷総合計"
        ship_grand_total[36] = format_num(shipping_total_all)
        grid.append(ship_grand_total)

    # === 右側集計枠の結合 ===
    for i in range(len(right_side_data)):
        rs_row = right_side_data[i]
        rs_padded = rs_row + [""] * max(0, 3 - len(rs_row))
        if i + 2 < len(grid):
            grid[i + 2][38] = rs_padded[0]
            grid[i + 2][39] = rs_padded[1]
            grid[i + 2][40] = rs_padded[2]
            
    return grid

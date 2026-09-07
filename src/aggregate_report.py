import pandas as pd
from typing import List, Any, Union, cast, Tuple, Optional
import logging
import unicodedata
import datetime

# --- 動的に MAJOR_CLIENTS を取得（テンプレート由来） ---
from mapping_definitions import MICRO_ROW_MAP
MAJOR_CLIENTS = set()
for k in MICRO_ROW_MAP.keys():
    if not any(x in k for x in ['そのた', '合計', 'HEADER', '＜', 'プレス', '⑤その他']):
        MAJOR_CLIENTS.add(k.split('_')[0])
# ---------------------------------------------------

logger = logging.getLogger(__name__)

YOKOMOCHI_KEYWORDS = ["富士", "浜松", "御殿場", "(横持)"]

# 新しいマッピングの追加
ITEM_TO_CATEGORY = {
    "段ボール": "①段ボール", "新聞": "②新聞", "雑誌": "③雑誌", 
    "PETボトル": "④プラ類", "ストレッチフィルム": "④プラ類", "シュリンクフィルム": "④プラ類", 
    "PPバンド": "④プラ類", "廃プラ軟質": "④プラ類", "プラスチックパレット": "④プラ類",
    "牛乳パック": "⑤その他", "雑古紙": "⑤その他", "雑がみ": "⑤その他", "ウエス": "⑤その他", 
    "台紙": "⑤その他", "模造": "⑤その他", "クラフト": "⑤その他", "窓付廃紙": "⑤その他", 
    "上白": "⑤その他", "紙パック": "⑤その他", "紙管": "⑤その他", "その他": "⑤その他"
}

from typing import Any, List, Dict

# --- 事務員が手入力する「値引き」「調整」等を元の品目に紐づけるためのリスト（案1） ---
# キー: 仕入先名の一部, 値: マッピング先の「大品目分類」
ADJUSTMENT_SUPPLIER_RULES: Dict[str, str] = {
    # 例: "株式会社〇〇": "①段ボール",
}

def transform_raw_data(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.select_dtypes(include=['object', 'string']).columns:
        df[col] = df[col].apply(
            lambda x: unicodedata.normalize('NFKC', x).replace(" ", "").replace("　", "") if isinstance(x, str) else x
        )
        
    import json
    import os
    alias_file = os.path.join(os.path.dirname(__file__), "..", "item_aliases.json")
    if os.path.exists(alias_file):
        try:
            with open(alias_file, "r", encoding="utf-8") as f:
                aliases = json.load(f)
            for alias in aliases:
                client_cond = alias.get("client_contains")
                item_cond = alias.get("item_in")
                replace_with = alias.get("replace_with")
                if client_cond and item_cond and replace_with:
                    mask_client = df["仕入先名"].astype(str).str.contains(client_cond) | df["支払先名"].astype(str).str.contains(client_cond)
                    mask_item = df["品名"].astype(str).isin(item_cond)
                    df.loc[mask_client & mask_item, "品名"] = replace_with
        except Exception as e:
            print(f"Warning: Failed to apply item_aliases.json: {e}")
        
    # --- 実重量の計算 (文字列からの数値変換を安全に行う) ---
    df["実重量"] = pd.to_numeric(df.get("正味重量", pd.Series([0]*len(df))).astype(str).str.replace(',', ''), errors='coerce').fillna(0) + \
                 pd.to_numeric(df.get("調整重量", pd.Series([0]*len(df))).astype(str).str.replace(',', ''), errors='coerce').fillna(0)
    
    df["横持フラグ"] = df["仕入先名"].apply(lambda x: any(kw in str(x) for kw in YOKOMOCHI_KEYWORDS) if pd.notna(x) else False)
    
    # --- 品目分類を経路分類より先に実行（プレス判定等で参照するため） ---
    def map_category(row: Any) -> str:
        item_str = str(row.get("品名", ""))
        
        # 1. 既存の品名による判定
        for k, v in ITEM_TO_CATEGORY.items():
            if k in item_str:
                return v
                
        # 2. 矛盾④対策：マイナス値または調整キーワードが含まれる場合のハイブリッド救済ロジック
        weight = float(row.get("実重量", 0))
        is_adjustment = weight < 0 or any(kw in item_str for kw in ["値引", "調整", "相殺", "ﾏｲﾅｽ", "マイナス"])
        
        if is_adjustment:
            # 案3: 備考欄を読んで判定
            note_str = str(row.get("備考", ""))
            for k, v in ITEM_TO_CATEGORY.items():
                if k in note_str:
                    return v
                    
            # 案1: 事前登録された仕入先リストによる判定
            supplier = str(row.get("仕入先名", ""))
            for sup_k, cat_v in ADJUSTMENT_SUPPLIER_RULES.items():
                if sup_k in supplier:
                    return cat_v
                    
        logger.warning(f"Unknown item mapped to ⑤その他: {item_str}")
        return "⑤その他"
        
    df["大品目分類"] = df.apply(map_category, axis=1)
    
    # --- 経路分類 ---
    def classify_route(row: Any) -> str:
        item_name = str(row.get("品名", ""))
        inout = str(row.get("自社他社区分", ""))
        customer = str(row.get("得意先名", ""))
        transaction_type = str(row.get("取引区分", ""))
        category = str(row.get("大品目分類", ""))
        
        if pd.notna(row.get("得意先名")) and customer.strip() not in ["", "None", "nan"]:
            if "輸出" in customer or "輸出" in str(row.get("備考", "")):
                return "輸出"
            return "国内"

        # 矛盾②対策: ④プラ類と⑤その他にはプレス枠がないためバラとして扱う
        if "プレス" in item_name and category not in ("④プラ類", "⑤その他"):
            return "プレス品"
            
        if "持込" in transaction_type:
            return "持込み"
            
        if "引取" in transaction_type:
            if "自社" in inout:
                return "自社回収"
            if "他社" in inout:
                return "他社回収"
                
        return "持込み"
        
    df["経路分類"] = df.apply(classify_route, axis=1)
    
    df["支払先名"] = df.get("支払先名", pd.Series([None]*len(df))).fillna("")
    df["仕入先名"] = df.get("仕入先名", pd.Series([None]*len(df))).fillna("")
    df["運送店名"] = df.get("運送店名", pd.Series([None]*len(df))).fillna("")
    df["得意先名"] = df.get("得意先名", pd.Series([None]*len(df))).fillna("")
    
    # 矛盾①対策: ⑤その他の品目は仕入先名を集約せず個別に保持する
    def map_supplier(sup: str, is_yokomochi: bool, category: str) -> str:
        if is_yokomochi or not sup: return sup
        if category == "⑤その他": return sup
        for mc in MAJOR_CLIENTS:
            if mc and mc in sup:
                return sup
        return "そのた"
    
    df["仕入先名"] = df.apply(lambda r: map_supplier(
        str(r.get("仕入先名", "")),
        bool(r.get("横持フラグ", False)),
        str(r.get("大品目分類", ""))
    ), axis=1)
    
    return df

MASTER_HIERARCHY: List[Any] = [
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
            {"route_id": "事業所間横持", "route_match": ["持込み", "自社回収", "他社回収", "プレス品"], "route_disp": "自社回収"}
        ]
    }
]

SHIPPING_HIERARCHY: List[Any] = [
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
    
    top_header: List[Any] = [None] * 16
    for ym, col_idx in ym_to_col.items():
        top_header[col_idx] = str(ym)
    top_header[15] = "前年同月差分"
    grid.append(top_header)
    
    for cat_info in MASTER_HIERARCHY:
        cat_id = cat_info["cat_id"]
        
        grid.append([cat_id] + [None] * 15)
        
        for route_info in cat_info["routes"]:
            route_id = route_info["route_id"]
            route_match_list = route_info["route_match"]
            
            if cat_id == "＜参考＞事業所間横持ち":
                route_df = df[df["横持フラグ"] == True].copy()
            else:
                route_df = df[(df["大品目分類"] == cat_id) & (df["経路分類"].isin(route_match_list)) & (df["横持フラグ"] == False)].copy()
            
            grid.append(["", route_id] + [None] * 14)
            
            route_totals = [0.0] * 14
            
            if not route_df.empty:
                if cat_id == "＜参考＞事業所間横持ち":
                    group_keys = ["仕入先名", "品名"]
                else:
                    group_keys = ["仕入先名"]

                grouped = route_df.groupby(group_keys)
                for keys, supp_df in sorted(grouped):
                    row_data: List[Any] = [None] * 16
                    row_data[0] = ""
                    
                    keys_tuple: Tuple[Any, ...] = keys if isinstance(keys, tuple) else (keys,)
                    
                    if cat_id == "＜参考＞事業所間横持ち":
                        origin = str(keys_tuple[0]).replace("(横持)", "").replace("事業所", "").strip()
                        row_data[1] = f"{origin}→厚木"
                    else:
                        row_data[1] = keys_tuple[0]
                        
                    ym_sums = supp_df.groupby("_ym")["実重量"].sum()
                    val_last_year = 0.0
                    val_this_month = 0.0
                    
                    for ym, weight in ym_sums.items():
                        if ym in ym_to_col:
                            c_idx = ym_to_col[ym]
                            row_data[c_idx] = format_num(float(weight))
                            route_totals[c_idx - 2] += float(weight)
                            
                            if len(unique_yms) == 13:
                                if ym == unique_yms[0]:
                                    val_last_year = float(weight)
                                elif ym == unique_yms[12]:
                                    val_this_month = float(weight)
                                    
                    if len(unique_yms) == 13:
                        diff = val_this_month - val_last_year
                        row_data[15] = format_num(diff)
                        route_totals[13] += diff
                    
                    grid.append(row_data)
                    
            subtotal: List[Any] = [None] * 16
            subtotal[0] = ""
            subtotal[1] = f"{route_id.split('.')[-1]}合計" if "." in route_id else f"{route_id}合計"
            for i in range(13):
                if route_totals[i] > 0 or (route_totals[i] < 0): 
                    subtotal[i + 2] = format_num(route_totals[i])
            subtotal[15] = format_num(route_totals[13])
            grid.append(subtotal)
            
        grid.append([None] * 16)
            
    return grid

def build_micro_report(df: pd.DataFrame, target_year: Optional[int] = None, target_month: Optional[int] = None) -> List[List[Any]]:
    grid: List[List[Any]] = []
    
    if "transaction_date" in df.columns:
        df["_date"] = pd.to_datetime(df["transaction_date"], errors="coerce")
        df["_day"] = df["_date"].dt.day
        df["_year"] = df["_date"].dt.year
        df["_month"] = df["_date"].dt.month
    else:
        df["_date"] = pd.NaT
        df["_day"] = pd.NaT
        df["_year"] = pd.NaT
        df["_month"] = pd.NaT
        
    valid_dates = df["_date"].dropna()
    year, month = target_year, target_month
    
    if year is None or month is None:
        year, month = 2026, 5
        if not valid_dates.empty:
            mode_date = valid_dates.dt.to_period("M").mode()
            if not mode_date.empty:
                year, month = int(mode_date.iloc[0].year), int(mode_date.iloc[0].month)
                
    if not df.empty and "_year" in df.columns:
        df = df[(df["_year"] == year) & (df["_month"] == month)].copy()
            
    row0: List[Any] = [None] * 41
    row0[3] = f"{month}月"
    grid.append(row0)
    
    row1: List[Any] = [None] * 41
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
    
    right_side_data: List[List[Any]] = []
    total_all = 0.0
    nyuka_total = 0.0
    
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
                
            h_row: List[Any] = [None] * 41
            h_row[0] = f"{cat_disp}-{route_disp}"
            grid.append(h_row)
            
            right_side_idx = len(right_side_data)
            right_side_data.append(["", route_id, ""])
            
            route_totals = [0.0] * 32
            
            if not route_df.empty:
                if cat_id == "＜参考＞事業所間横持ち":
                    group_keys = ["仕入先名", "品名"]
                else:
                    group_keys = ["支払先名", "仕入先名", "運送店名", "品名"]

                grouped = route_df.groupby(group_keys)
                
                for keys, supp_df in sorted(grouped):
                    r_data: List[Any] = [None] * 41
                    
                    keys_tuple: Tuple[Any, ...] = keys if isinstance(keys, tuple) else (keys,)
                    
                    if cat_id == "＜参考＞事業所間横持ち":
                        if len(keys_tuple) >= 2:
                            origin = str(keys_tuple[0]).replace("(横持)", "").replace("事業所", "").strip()
                            r_data[1] = f"{origin}→厚木"
                            r_data[3] = keys_tuple[1]
                        else:
                            origin = str(keys_tuple[0]).replace("(横持)", "").replace("事業所", "").strip()
                            r_data[1] = f"{origin}→厚木"
                            r_data[3] = ""
                    else:
                        if len(keys_tuple) >= 4:
                            r_data[0] = keys_tuple[0] 
                            r_data[1] = keys_tuple[1] 
                            r_data[2] = keys_tuple[2] 
                            if cat_id == "⑤その他":
                                r_data[3] = keys_tuple[3] 
                            else:
                                r_data[3] = ""
                        else:
                            r_data[0] = str(keys_tuple[0])
                            r_data[3] = ""
                    
                    r_data[4] = "持込" if "持込" in route_disp else "引取"
                    
                    row_total = 0.0
                    day_sums = supp_df.groupby("_day")["実重量"].sum()
                    for day_key, weight in day_sums.items():
                        if pd.notna(cast(Any, day_key)) and 1 <= int(str(day_key)) <= 31:
                            r_data[4 + int(str(day_key))] = format_num(float(weight))
                            row_total += float(weight)
                            route_totals[int(str(day_key))] += float(weight)
                            
                    r_data[36] = format_num(row_total)
                    route_totals[0] += row_total
                    grid.append(r_data)
                    
                    if len(keys_tuple) >= 2:
                        disp_supplier = keys_tuple[1] if keys_tuple[1] else keys_tuple[0]
                    else:
                        disp_supplier = str(keys_tuple[0])
                        
                    right_side_data.append(["", disp_supplier, format_num(row_total)])
                    
            subtotal: List[Any] = [None] * 41
            subtotal_label = f"{route_id.split('.')[-1]}合計" if "." in route_id else f"{route_id}合計"
            subtotal[4] = subtotal_label
            for d in range(1, 32):
                if route_totals[d] > 0 or route_totals[d] < 0:
                    subtotal[4 + d] = format_num(route_totals[d])
            subtotal[36] = format_num(route_totals[0])
            grid.append(subtotal)
            
            cat_total += route_totals[0]
            right_side_data[right_side_idx][2] = format_num(route_totals[0])
            
        cat_total_row: List[Any] = [None] * 41
        cat_total_row[4] = f"{cat_disp}合計"
        cat_total_row[36] = format_num(cat_total)
        grid.append(cat_total_row)
        
        grid.append([None] * 41)
        
        total_all += cat_total
        if cat_id != "＜参考＞事業所間横持ち":
            nyuka_total += cat_total
            
        if cat_id == "⑤その他":
            nyuka_total_row: List[Any] = [None] * 41
            nyuka_total_row[4] = "入荷合計(横持除く)"
            nyuka_total_row[36] = format_num(nyuka_total)
            grid.append(nyuka_total_row)
            grid.append([None] * 41)
        
    grand_total: List[Any] = [None] * 41
    grand_total[4] = "入荷総合計"
    grand_total[36] = format_num(total_all)
    grid.append(grand_total)
    grid.append([None] * 41)
    
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
                r_data_ship: List[Any] = [None] * 41
                keys_tuple_ship: Tuple[Any, ...] = keys if isinstance(keys, tuple) else (keys,)
                
                if len(keys_tuple_ship) >= 2:
                    r_data_ship[1] = keys_tuple_ship[0] 
                    r_data_ship[3] = keys_tuple_ship[1] 
                else:
                    r_data_ship[1] = str(keys_tuple_ship[0])
                
                row_total = 0.0
                day_sums = supp_df.groupby("_day")["実重量"].sum()
                for day_key, weight in day_sums.items():
                    if pd.notna(cast(Any, day_key)) and 1 <= int(str(day_key)) <= 31:
                        r_data_ship[4 + int(str(day_key))] = format_num(float(weight))
                        row_total += float(weight)
                        route_totals[int(str(day_key))] += float(weight)
                        
                r_data_ship[36] = format_num(row_total)
                route_totals[0] += row_total
                grid.append(r_data_ship)
                
            subtotal_ship: List[Any] = [None] * 41
            subtotal_ship[1] = f"{route_id.split('.')[-1]}合計"
            for d in range(1, 32):
                if route_totals[d] > 0 or route_totals[d] < 0:
                    subtotal_ship[4 + d] = format_num(route_totals[d])
            subtotal_ship[36] = format_num(route_totals[0])
            grid.append(subtotal_ship)
            grid.append([None] * 41)
            
            cat_total += route_totals[0]
            
        if cat_total > 0:
            cat_total_row_ship: List[Any] = [None] * 41
            cat_total_row_ship[1] = f"{cat_disp}出荷合計"
            cat_total_row_ship[36] = format_num(cat_total)
            grid.append(cat_total_row_ship)
            grid.append([None] * 41)
            shipping_total_all += cat_total
            
    if shipping_total_all > 0:
        ship_grand_total: List[Any] = [None] * 41
        ship_grand_total[1] = "出荷総合計"
        ship_grand_total[36] = format_num(shipping_total_all)
        grid.append(ship_grand_total)

    for i in range(len(right_side_data)):
        rs_row = right_side_data[i]
        rs_padded = rs_row + [""] * max(0, 3 - len(rs_row))
        if i + 2 < len(grid):
            grid[i + 2][38] = rs_padded[0]
            grid[i + 2][39] = rs_padded[1]
            grid[i + 2][40] = rs_padded[2]
            
    return grid

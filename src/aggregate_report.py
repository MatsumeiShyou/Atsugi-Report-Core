import pandas as pd
from typing import List, Any, Union, cast, Tuple, Optional, Dict
import logging
import unicodedata
import datetime

# --- 主要取引先リスト ---
from mapping_definitions import MAJOR_CLIENTS_LIST
MAJOR_CLIENTS = set(MAJOR_CLIENTS_LIST)
# ---------------------------------------------------

logger = logging.getLogger(__name__)

YOKOMOCHI_KEYWORDS = ["(横持)"]



# 新しいマッピングの追加
ITEM_TO_CATEGORY = {
    "段ボール": "①段ボール", "E段": "①段ボール",
    "新聞": "②新聞",
    "雑誌": "③雑誌", "雑古紙": "③雑誌", "雑がみ": "③雑誌", "ミックス紙": "③雑誌",
    "PETボトル": "④プラ類", "ペットボトル": "④プラ類", "ストレッチフィルム": "④プラ類", "シュリンクフィルム": "④プラ類", 
    "PPバンド": "④プラ類", "廃プラ軟質": "④プラ類", "プラスチックパレット": "④プラ類", "フイルム": "④プラ類", "フィルム": "④プラ類",
    "牛乳パック": "⑤その他", "ウエス": "⑤その他", "台紙": "⑤その他", "上台紙": "⑤その他",
    "模造": "⑤その他", "クラフト": "⑤その他", "色クラフト": "⑤その他", "窓付廃紙": "⑤その他", 
    "上白": "⑤その他", "紙パック": "⑤その他", "紙管": "⑤その他", "シュレッダー": "⑤その他",
    "ケント": "⑤その他", "上ケント": "⑤その他", "損紙": "⑤その他", "白・色混り": "⑤その他",
    "ワンプ": "⑤その他", "カップ原紙": "⑤その他", "マルチパック": "⑤その他", "その他": "⑤その他",
    "糊付廃紙": "⑤その他",
    "雑袋": "⑤その他",
    "布類": "⑤その他",
    "ライナー巻取": "⑤その他",
    "色上": "⑤その他",
    "アルミ缶": "⑤その他",
    "機密書類": "⑤その他",
    "色上 ハーゼスト": "⑤その他",
    "袋茶プレス": "⑤その他",
    "荷潰し品": "⑤その他",
    "雑袋プレス": "⑤その他",
    "機密書類 相模野病院": "⑤その他",
    "パルプ": "⑤その他",
    "鉄くず": "⑤その他",
    "機密書類 アサヒロジスティクス": "⑤その他",
    "難処理古紙プレス": "⑤その他",
    "トレーシングペーパー": "⑤その他",
    "切茶": "⑤その他",
    "セロハン巻取": "⑤その他",
    "セロハン巻取(三和機工)": "⑤その他",
    "巻取": "⑤その他",
    "巻取@38": "⑤その他",
    "機密書類 木下カンセー": "⑤その他",
    "軟質ミックス 仁和包装": "⑤その他",
    "機密書類 コーナン鎌倉大船モー": "⑤その他",
    "軟質ミックス": "⑤その他",
    "軟質ミックスプレス": "⑤その他"
}

def is_outbound_transaction(row: pd.Series) -> bool:
    """
    取引区分、デ区、得意先名から出荷（売上）トランザクションを確定的に判定する。
    """
    de_ku = str(row.get("デ区", "")).strip()
    tokuisaki = str(row.get("得意先名", "")).strip()
    torihiki = str(row.get("取引区分", "")).strip()
    
    if "売上" in de_ku or "売上" in torihiki or "出荷" in torihiki:
        return True
    if bool(tokuisaki) and tokuisaki.lower() not in ("nan", "none", ""):
        return True
    return False

def classify_outbound_route(row: pd.Series) -> str:
    """
    出荷（売上）トランザクションを「1.輸出」または「2.国内」に分類する。
    ユーザー指定により、輸出となる条件は得意先名が「坪野谷紙業貿易部」であることのみとする。
    """
    client = str(row.get("得意先名", "")).strip()
    
    if "坪野谷紙業貿易部" in client:
        return "1.輸出"
    return "2.国内"

def transform_raw_data(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    生データをクレンジングし、入出荷物理分離（Split-Pipeline Pattern）を行って
    (df_inbound, df_outbound) のタプルを返す。
    """
    if df.empty:
        return df.copy(), df.copy()

    df = df.copy()
    for c in ["仕入先名", "支払先名", "運送店名", "得意先名", "品名", "取引区分", "デ区", "自社他社区分", "備考"]:
        if c not in df.columns:
            df[c] = ""

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
            
    # 厚木事業所（ヤードコード27）のデータのみを抽出
    if "ヤードコード" in df.columns:
        df = df[df["ヤードコード"].astype(str) == "27"].copy()
    elif "ヤード名" in df.columns:
        df = df[df["ヤード名"].astype(str).str.contains("厚木", na=False)].copy()
        
    # 非重量商品（運搬料や取扱手数料など）の除外
    if "品名" in df.columns:
        df = df[~df["品名"].astype(str).str.contains("運搬|取扱|手数料|加工賃|紹介料|リース|機密 ブリヂストン~丸富製紙|機密 ブリヂストン~鶴見沼津", na=False)].copy()
        
    # --- 非物理会計調整伝票の除外ゲート（U-NET月末運賃・補助金伝票の二重計上防止） ---
    raw_net = pd.to_numeric(df.get("正味重量", pd.Series([0]*len(df))).astype(str).str.replace(',', ''), errors='coerce').fillna(0)
    payee_str = df.get("支払先名", pd.Series([""]*len(df))).astype(str)
    supp_str = df.get("仕入先名", pd.Series([""]*len(df))).astype(str)
    item_str = df.get("品名", pd.Series([""]*len(df))).astype(str)
    
    mask_non_physical = (
        (raw_net == 0) &
        (
            payee_str.str.contains("U-NET|ユーネット", na=False) |
            supp_str.str.contains("U-NET|ユーネット|運賃|運搬補助", na=False) |
            item_str.str.contains("運賃|運搬補助|補助金", na=False)
        )
    )
    df = df[~mask_non_physical].copy()

    # --- 実重量の計算 (文字列からのカンマ削除・数値変換を安全に行う) ---
    df["実重量"] = pd.to_numeric(df.get("正味重量", pd.Series([0]*len(df))).astype(str).str.replace(',', ''), errors='coerce').fillna(0) + \
                 pd.to_numeric(df.get("調整重量", pd.Series([0]*len(df))).astype(str).str.replace(',', ''), errors='coerce').fillna(0)

    # --- 入出荷物理分離（Split-Pipeline Pattern） ---
    is_outbound_mask = df.apply(is_outbound_transaction, axis=1)
    df_inbound = df[~is_outbound_mask].copy()
    df_outbound = df[is_outbound_mask].copy()

    df_inbound["横持フラグ"] = df_inbound["仕入先名"].apply(lambda x: any(kw in str(x) for kw in YOKOMOCHI_KEYWORDS) if pd.notna(x) else False)
    df_outbound["横持フラグ"] = False
    
    # --- 品目分類 ---
    def map_category(row: Any) -> str:
        if row.get("横持フラグ") == True:
            return "＜参考＞事業所間横持ち"

        item_str = str(row.get("品名", ""))
        for k, v in ITEM_TO_CATEGORY.items():
            if k in item_str:
                return v
                
        weight = float(row.get("実重量", 0))
        is_adjustment = weight < 0 or any(kw in item_str for kw in ["値引", "調整", "相殺", "ﾃﾝﾋﾞｷ", "マイナス"])
        
        if is_adjustment:
            note_str = str(row.get("備考", ""))
            for k, v in ITEM_TO_CATEGORY.items():
                if k in note_str:
                    return v
                    
        logger.warning(f"Unknown item mapped to ⑤その他: {item_str}")
        return "⑤その他"
        
    df_inbound["大品目分類"] = df_inbound.apply(map_category, axis=1)
    df_outbound["大品目分類"] = df_outbound.apply(map_category, axis=1)
    
    # --- 入荷経路分類 ---
    def classify_route(row: Any) -> str:
        item_name = str(row.get("品名", ""))
        inout = str(row.get("自社他社区分", ""))
        transaction_type = str(row.get("取引区分", ""))

        if "プレス" in item_name:
            return "プレス品"
            
        if "持込" in transaction_type:
            return "持込み"
            
        if "引取" in transaction_type:
            if "自社" in inout:
                return "自社回収"
            if "他社" in inout:
                return "他社回収"
                
        return "持込み"
        
    df_inbound["経路分類"] = df_inbound.apply(classify_route, axis=1)
    df_outbound["経路分類"] = df_outbound.apply(classify_outbound_route, axis=1)
    
    # --- 不変データ射影（店舗リネージ保持と管理会社正規化） ---
    def map_supplier(sup: str, is_yokomochi: bool, category: str) -> str:
        if is_yokomochi or not sup: return sup
        if category == "⑤その他": return sup
        for mc in MAJOR_CLIENTS:
            if mc and mc in sup:
                return sup
        return "そのた"
    
    df_inbound["store_name"] = df_inbound["仕入先名"].fillna("").astype(str).str.strip()
    df_inbound["payee_name"] = df_inbound["支払先名"].fillna("").astype(str).str.strip()
    
    df_inbound["normalized_parent"] = df_inbound.apply(
        lambda r: map_supplier(
            r["payee_name"] if r["payee_name"] else r["store_name"],
            bool(r.get("横持フラグ", False)),
            str(r.get("大品目分類", ""))
        ),
        axis=1
    )
    
    df_outbound["client_name"] = df_outbound["得意先名"].fillna("").astype(str).str.strip()
    df_outbound["spec_name"] = df_outbound["品名"].fillna("").astype(str).str.strip()
    
    return df_inbound, df_outbound

MASTER_HIERARCHY: List[Any] = [
    {
        "cat_id": "①段ボール", "cat_disp": "段ボール",
        "routes": [
            {"route_id": "1.持込み・バラ", "route_match": ["持込み"], "route_disp": "持込"},
            {"route_id": "2.引取り・バラ(自社)", "route_match": ["自社回収"], "route_disp": "自社回収"},
            {"route_id": "3.引取り・バラ(他社)", "route_match": ["他社回収"], "route_disp": "他社回収"},
            {"route_id": "4.その他・プレス", "route_match": ["プレス品"], "route_disp": "プレス品"}
        ]
    },
    {
        "cat_id": "②新聞", "cat_disp": "新聞",
        "routes": [
            {"route_id": "1.持込み・バラ", "route_match": ["持込み"], "route_disp": "持込"},
            {"route_id": "2.引取り・バラ(自社)", "route_match": ["自社回収"], "route_disp": "自社回収"},
            {"route_id": "3.引取り・バラ(他社)", "route_match": ["他社回収"], "route_disp": "他社回収"},
            {"route_id": "4.その他・プレス", "route_match": ["プレス品"], "route_disp": "プレス品"}
        ]
    },
    {
        "cat_id": "③雑誌", "cat_disp": "雑誌",
        "routes": [
            {"route_id": "1.持込み・バラ", "route_match": ["持込み"], "route_disp": "持込"},
            {"route_id": "2.引取り・バラ(自社)", "route_match": ["自社回収"], "route_disp": "自社回収"},
            {"route_id": "3.引取り・バラ(他社)", "route_match": ["他社回収"], "route_disp": "他社回収"},
            {"route_id": "4.その他・プレス", "route_match": ["プレス品"], "route_disp": "プレス品"}
        ]
    },
    {
        "cat_id": "④プラ類", "cat_disp": "プラ類",
        "routes": [
            {"route_id": "1.持込み・バラ", "route_match": ["持込み"], "route_disp": "持込"},
            {"route_id": "2.引取り・バラ(自社)", "route_match": ["自社回収"], "route_disp": "自社回収"},
            {"route_id": "3.引取り・バラ(他社)", "route_match": ["他社回収"], "route_disp": "他社回収"},
            {"route_id": "4.その他・プレス", "route_match": ["プレス品"], "route_disp": "プレス品"}
        ]
    },
    {
        "cat_id": "⑤その他", "cat_disp": "その他",
        "routes": [
            {"route_id": "1.持込み・バラ", "route_match": ["持込み"], "route_disp": "持込"},
            {"route_id": "2.引取り・バラ(自社)", "route_match": ["自社回収"], "route_disp": "自社回収"},
            {"route_id": "3.引取り・バラ(他社)", "route_match": ["他社回収"], "route_disp": "他社回収"},
            {"route_id": "4.その他・プレス", "route_match": ["プレス品"], "route_disp": "プレス品"}
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
            {"route_id": "1.輸出", "route_match": ["1.輸出", "輸出"], "route_disp": "輸出"},
            {"route_id": "2.国内", "route_match": ["2.国内", "国内"], "route_disp": "国内"}
        ]
    },
    {
        "cat_id": "②新聞", "cat_disp": "新聞",
        "routes": [
            {"route_id": "1.輸出", "route_match": ["1.輸出", "輸出"], "route_disp": "輸出"},
            {"route_id": "2.国内", "route_match": ["2.国内", "国内"], "route_disp": "国内"}
        ]
    },
    {
        "cat_id": "③雑誌", "cat_disp": "雑誌",
        "routes": [
            {"route_id": "1.輸出", "route_match": ["1.輸出", "輸出"], "route_disp": "輸出"},
            {"route_id": "2.国内", "route_match": ["2.国内", "国内"], "route_disp": "国内"}
        ]
    },
    {
        "cat_id": "④プラ類", "cat_disp": "プラ類",
        "routes": [
            {"route_id": "1.輸出", "route_match": ["1.輸出", "輸出"], "route_disp": "輸出"},
            {"route_id": "2.国内", "route_match": ["2.国内", "国内"], "route_disp": "国内"}
        ]
    },
    {
        "cat_id": "⑤その他", "cat_disp": "その他",
        "routes": [
            {"route_id": "1.輸出", "route_match": ["1.輸出", "輸出"], "route_disp": "輸出"},
            {"route_id": "2.国内", "route_match": ["2.国内", "国内"], "route_disp": "国内"}
        ]
    }
]

def format_num(val: float) -> str:
    if val == 0:
        return "0"
    return f"{int(val):,}"

def build_macro_report(
    df_inbound: pd.DataFrame,
    df_outbound: Optional[pd.DataFrame] = None,
    target_year: Optional[int] = None,
    target_month: Optional[int] = None
) -> List[List[Any]]:
    grid: List[List[Any]] = []
    
    df_in = df_inbound.copy()
    if "transaction_date" in df_in.columns:
        df_in["_date"] = pd.to_datetime(df_in["transaction_date"], errors="coerce")
        df_in["_ym"] = df_in["_date"].dt.to_period("M")
    else:
        df_in["_date"] = pd.NaT
        df_in["_ym"] = pd.NaT

    if target_year is None or target_month is None:
        target_year, target_month = 2026, 8
        valid_dates = df_in["_date"].dropna()
        if not valid_dates.empty:
            mode_date = valid_dates.dt.to_period("M").mode()
            if not mode_date.empty:
                target_year, target_month = int(mode_date.iloc[0].year), int(mode_date.iloc[0].month)
                
    # 決定論的13ヶ月カレンダーウィンドウの生成 (当月がインデックス12、前年同月がインデックス0)
    target_period = pd.Period(f"{target_year:04d}-{target_month:02d}", freq="M")
    unique_yms = [target_period - 12 + i for i in range(13)]
        
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
                route_df = df_in[df_in["横持フラグ"] == True].copy()
            else:
                route_df = df_in[(df_in["大品目分類"] == cat_id) & (df_in["経路分類"].isin(route_match_list)) & (df_in["横持フラグ"] == False)].copy()
            
            grid.append(["", route_id] + [None] * 14)
            
            route_totals = [0.0] * 14
            
            if not route_df.empty:
                if cat_id == "＜参考＞事業所間横持ち":
                    group_keys = ["仕入先名", "品名"]
                else:
                    group_keys = ["normalized_parent"] if "normalized_parent" in route_df.columns else ["仕入先名"]

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
                    
                    for ym_val, weight in ym_sums.items():
                        ym = cast(pd.Period, ym_val)
                        if ym in ym_to_col:
                            c_idx = ym_to_col[ym]
                            row_data[c_idx] = format_num(float(weight))
                            route_totals[c_idx - 2] += float(weight)
                            
                            if ym == unique_yms[0]:
                                val_last_year = float(weight)
                            elif ym == unique_yms[12]:
                                val_this_month = float(weight)
                                    
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
        
    # --- 出荷推移ブロック (SHIPPING_HIERARCHY) ---
    if df_outbound is not None and not df_outbound.empty:
        df_out = df_outbound.copy()
        if "transaction_date" in df_out.columns:
            df_out["_date"] = pd.to_datetime(df_out["transaction_date"], errors="coerce")
            df_out["_ym"] = df_out["_date"].dt.to_period("M")
        else:
            df_out["_date"] = pd.NaT
            df_out["_ym"] = pd.NaT
            
        grid.append(["＜出荷＞"] + [None] * 15)
        
        for cat_info in SHIPPING_HIERARCHY:
            cat_id = cat_info["cat_id"]
            cat_disp = cat_info["cat_disp"]
            
            grid.append(["", cat_id] + [None] * 14)
            cat_shipping_totals = [0.0] * 14
            
            for route_info in cat_info["routes"]:
                route_id = route_info["route_id"]
                route_match_list = route_info["route_match"]
                route_disp = route_info["route_disp"]
                
                route_df = df_out[(df_out["大品目分類"] == cat_id) & (df_out["経路分類"].isin(route_match_list))].copy()
                grid.append(["", route_id] + [None] * 14)
                route_totals = [0.0] * 14
                
                if not route_df.empty:
                    group_keys = ["client_name", "spec_name"] if "client_name" in route_df.columns else ["得意先名", "品名"]
                    grouped = route_df.groupby(group_keys)
                    for keys, supp_df in sorted(grouped):
                        ship_row_data: List[Any] = [None] * 16
                        ship_row_data[0] = ""
                        keys_tuple = keys if isinstance(keys, tuple) else (keys,)
                        ship_row_data[1] = f"{keys_tuple[0]} {keys_tuple[1]}".strip() if len(keys_tuple) >= 2 else str(keys_tuple[0])
                        
                        ym_sums = supp_df.groupby("_ym")["実重量"].sum()
                        val_last_year = 0.0
                        val_this_month = 0.0
                        for ym_val, weight in ym_sums.items():
                            ym = cast(pd.Period, ym_val)
                            if ym in ym_to_col:
                                c_idx = ym_to_col[ym]
                                ship_row_data[c_idx] = format_num(float(weight))
                                route_totals[c_idx - 2] += float(weight)
                                if ym == unique_yms[0]: val_last_year = float(weight)
                                elif ym == unique_yms[12]: val_this_month = float(weight)
                        ship_row_data[15] = format_num(val_this_month - val_last_year)
                        route_totals[13] += (val_this_month - val_last_year)
                        grid.append(ship_row_data)
                        
                ship_subtotal: List[Any] = [None] * 16
                ship_subtotal[1] = f"{route_disp}合計"
                for i in range(13):
                    if route_totals[i] != 0: ship_subtotal[i + 2] = format_num(route_totals[i])
                ship_subtotal[15] = format_num(route_totals[13])
                grid.append(ship_subtotal)
                for i in range(14): cat_shipping_totals[i] += route_totals[i]
                
            cat_subtotal: List[Any] = [None] * 16
            cat_subtotal[1] = f"{cat_disp}出荷合計"
            for i in range(13):
                if cat_shipping_totals[i] != 0: cat_subtotal[i + 2] = format_num(cat_shipping_totals[i])
            cat_subtotal[15] = format_num(cat_shipping_totals[13])
            grid.append(cat_subtotal)
            grid.append([None] * 16)
            
    return grid

def build_micro_report(
    df_inbound: pd.DataFrame,
    df_outbound: Optional[pd.DataFrame] = None,
    target_year: Optional[int] = None,
    target_month: Optional[int] = None
) -> List[List[Any]]:
    grid: List[List[Any]] = []
    
    df_in = df_inbound.copy()
    if "transaction_date" in df_in.columns:
        df_in["_date"] = pd.to_datetime(df_in["transaction_date"], errors="coerce")
        df_in["_day"] = df_in["_date"].dt.day
        df_in["_year"] = df_in["_date"].dt.year
        df_in["_month"] = df_in["_date"].dt.month
    else:
        df_in["_date"] = pd.NaT
        df_in["_day"] = pd.NaT
        df_in["_year"] = pd.NaT
        df_in["_month"] = pd.NaT
        
    year, month = target_year, target_month
    
    if year is None or month is None:
        year, month = 2026, 8
        valid_dates = df_in["_date"].dropna()
        if not valid_dates.empty:
            mode_date = valid_dates.dt.to_period("M").mode()
            if not mode_date.empty:
                year, month = int(mode_date.iloc[0].year), int(mode_date.iloc[0].month)
                
    if not df_in.empty and "_year" in df_in.columns:
        df_in = df_in[(df_in["_year"] == year) & (df_in["_month"] == month)].copy()
            
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
                route_df = df_in[df_in["横持フラグ"] == True].copy()
            else:
                route_df = df_in[(df_in["大品目分類"] == cat_id) & (df_in["経路分類"].isin(route_match_list)) & (df_in["横持フラグ"] == False)].copy()
                
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
                        origin = str(keys_tuple[0]).replace("(横持)", "").replace("事業所", "").strip()
                        r_data[1] = f"{origin}→厚木"
                        r_data[3] = keys_tuple[1] if len(keys_tuple) >= 2 else ""
                    else:
                        if len(keys_tuple) >= 4:
                            r_data[0] = keys_tuple[0] 
                            r_data[1] = keys_tuple[1] 
                            r_data[2] = keys_tuple[2] 
                            r_data[3] = keys_tuple[3]  # Directive 1: PRESERVED for all categories!
                        else:
                            r_data[0] = str(keys_tuple[0])
                            r_data[3] = str(keys_tuple[1]) if len(keys_tuple) > 1 else ""
                    
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
                    
                    disp_supplier = keys_tuple[1] if (len(keys_tuple) >= 2 and keys_tuple[1]) else str(keys_tuple[0])
                    disp_item = str(keys_tuple[3]) if len(keys_tuple) >= 4 else (str(keys_tuple[1]) if len(keys_tuple) >= 2 and cat_id == "＜参考＞事業所間横持ち" else "")
                    right_side_data.append([disp_supplier, disp_item, format_num(row_total)])
                    
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
    
    # --- Directive 1: 出荷セクションの完全実装 (df_outbound) ---
    grid.append(["＜出荷＞"] + [None]*40)
    
    shipping_total_all = 0.0
    if df_outbound is not None and not df_outbound.empty:
        df_out = df_outbound.copy()
        if "transaction_date" in df_out.columns:
            df_out["_date"] = pd.to_datetime(df_out["transaction_date"], errors="coerce")
            df_out["_day"] = df_out["_date"].dt.day
            df_out["_year"] = df_out["_date"].dt.year
            df_out["_month"] = df_out["_date"].dt.month
            df_out = df_out[(df_out["_year"] == year) & (df_out["_month"] == month)].copy()
        else:
            df_out = df_out.iloc[0:0].copy()

        for cat_info in SHIPPING_HIERARCHY:
            cat_id = cat_info["cat_id"]
            cat_disp = cat_info["cat_disp"]
            cat_total = 0.0
            
            has_cat_header = False
            
            for route_info in cat_info["routes"]:
                route_id = route_info["route_id"]
                route_match_list = route_info["route_match"]
                
                route_df = df_out[(df_out["大品目分類"] == cat_id) & (df_out["経路分類"].isin(route_match_list))].copy()
                if route_df.empty:
                    continue
                    
                if not has_cat_header:
                    grid.append(["", cat_id] + [None]*39)
                    has_cat_header = True
                    
                grid.append(["", route_id] + [None]*39)
                
                route_totals = [0.0] * 32
                
                group_keys = ["client_name", "spec_name"] if "client_name" in route_df.columns else ["得意先名", "品名"]
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

def generate_warnings(df: pd.DataFrame) -> str:
    unknown_items = []
    for idx, row in df.iterrows():
        if row.get("大品目分類") == "⑤その他":
            item_str = str(row.get("品名", ""))
            is_mapped = False
            for k, v in ITEM_TO_CATEGORY.items():
                if k in item_str and v == "⑤その他":
                    is_mapped = True
                    break
            if not is_mapped:
                note_str = str(row.get("備考", ""))
                for k, v in ITEM_TO_CATEGORY.items():
                    if k in note_str and v == "⑤その他":
                        is_mapped = True
                        break
            if not is_mapped:
                unknown_items.append(row)
                
    if not unknown_items:
        return ""
        
    unknown_df = pd.DataFrame(unknown_items)
    total_count = len(unknown_df)
    total_weight = unknown_df["実重量"].astype(float).sum()
    
    lines = [
        "【注意】",
        f"未登録の品名が {total_count}件（合計 {total_weight:,.0f}kg）含まれています。",
        "分類先は「⑤その他」です。",
        "",
        "対象品名:"
    ]
    
    unique_items = unknown_df.groupby("品名").agg(
        count=("品名", "count"),
        weight=("実重量", lambda x: x.astype(float).sum())
    ).reset_index()
    
    for _, row in unique_items.iterrows():
        lines.append(f"- {row['品名']} ({row['count']}件, {row['weight']:,.0f}kg)")
        
    return "\n".join(lines)

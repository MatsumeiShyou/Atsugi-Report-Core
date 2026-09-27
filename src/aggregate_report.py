import pandas as pd
from typing import List, Any, Union, cast, Tuple, Optional, Dict
import logging
import unicodedata
import datetime

# --- 主要取引先リスト ---
from mapping_definitions import ITEM_CATEGORY_MAP
# ---------------------------------------------------

logger = logging.getLogger(__name__)

YOKOMOCHI_KEYWORDS = ["(横持)"]





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


def purge_zero_sum_groups(df: pd.DataFrame, is_inbound: bool) -> pd.DataFrame:
    '''
    期間スライス済みのデータフレームを受け取り、
    指定された期間（当月のみ、あるいは13ヶ月間など）の全期間を通じて
    実重量の合計が 0 となる業者（および品名・経路）のグループを
    完全に除外（パージ）する。
    これにより、下流の出力関数でのゼロ除外パッチが不要になる。
    '''
    if df.empty:
        return df
        
    temp_df = df.copy()
    if is_inbound:
        group_keys = ["normalized_parent", "大品目分類", "経路分類", "品名"]
    else:
        group_keys = ["client_name", "大品目分類", "経路分類", "spec_name"]
        
    actual_keys = [k for k in group_keys if k in temp_df.columns]
    
    if not actual_keys:
        return df

    # グループごとの合計重量を計算し、全行にブロードキャスト
    sums_per_row = temp_df.groupby(actual_keys, dropna=False)["実重量"].transform("sum")
    
    # 合計が 0 ではない行（意味のある実績データ）のみを残す
    keep_mask = sums_per_row != 0
    return df[keep_mask].copy()


def transform_raw_data(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    生データをクレンジングし、入出荷物理分離（Split-Pipeline Pattern）を行って
    (df_inbound, df_outbound) のタプルを返す。
    """
    if df.empty:
        return df.copy(), df.copy()

    import unicodedata
    df = df.copy()
    df.columns = [unicodedata.normalize('NFKC', str(c)).replace(' ', '').replace('　', '') for c in df.columns]

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
        
    # --- 1. 明示的な除外（人間が定義した除外キーワード） ---
    # ※全角半角・カタカナの揺れは上部の NFKC 正規化で吸収済み。
    # ※大文字小文字の揺れを吸収するため、全て upper() にして比較する。
    try:
        from supabase_client import fetch_rule_master
        rules_db = fetch_rule_master()
        black_list = rules_db.get("BLACK", [])
        white_list = rules_db.get("WHITE", [])
    except Exception:
        black_list = []
        white_list = []

    exclude_item_keywords = ["運搬", "取扱", "手数料", "加工賃", "紹介料", "リース", "機密 ブリヂストン~丸富製紙", "機密 ブリヂストン~鶴見沼津", "補助金"] + black_list
    exclude_vendor_keywords = ["U-NET", "ユーネット", "運賃", "運搬"] + black_list

    item_str = df.get("品名", pd.Series([""]*len(df))).astype(str).str.upper()
    supp_str = df.get("仕入先名", pd.Series([""]*len(df))).astype(str).str.upper()
    payee_str = df.get("支払先名", pd.Series([""]*len(df))).astype(str).str.upper()

    mask_exclude_item = item_str.str.contains("|".join(exclude_item_keywords).upper(), na=False, regex=True)
    mask_exclude_vendor = supp_str.str.contains("|".join(exclude_vendor_keywords).upper(), na=False, regex=True) | \
                          payee_str.str.contains("|".join(exclude_vendor_keywords).upper(), na=False, regex=True)
                          
    mask_exclude = mask_exclude_item | mask_exclude_vendor

    # アンビエンテの仕入調整（非重量伝票）を除外
    mask_ambiente_dummy = (df["仕入先名"].str.contains("アンビエンテ|ｱﾝﾋﾞｴﾝﾃ", na=False)) & (df["デ区"] == "仕入調整")
    mask_exclude = mask_exclude | mask_ambiente_dummy

    # ホワイトリスト（許可）はブラックリスト（除外）よりも優先される（救済）
    if white_list:
        mask_white_item = item_str.str.contains("|".join(white_list).upper(), na=False, regex=True)
        mask_white_vendor = supp_str.str.contains("|".join(white_list).upper(), na=False, regex=True) | \
                            payee_str.str.contains("|".join(white_list).upper(), na=False, regex=True)
        mask_exclude = mask_exclude & ~(mask_white_item | mask_white_vendor)

    # 除外確定
    df = df[~mask_exclude].copy()

    # --- 実重量の計算 (文字列からのカンマ削除・数値変換を安全に行う) ---
    raw_net_s = pd.to_numeric(df.get("正味重量", pd.Series([0]*len(df))).astype(str).str.replace(',', ''), errors='coerce').fillna(0)
    raw_adj_s = pd.to_numeric(df.get("調整重量", pd.Series([0]*len(df))).astype(str).str.replace(',', ''), errors='coerce').fillna(0)
    df["実重量"] = raw_net_s + raw_adj_s

    # --- 2. 怪しいデータの検知と警告（システムが人間に判断を仰ぐ） ---
    # 金額や単価がゼロ、または正味重量がゼロの伝票はダミー（調整）の可能性が高いため、ログに出力して人間に知らせる。
    if "金額" in df.columns:
        amt_s = pd.to_numeric(df["金額"].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
        suspicious_mask = ((amt_s == 0) & (df["実重量"] > 0)) | ((raw_net_s == 0) & (raw_adj_s != 0))
        
        # ホワイトリストに登録されているものは警告から外す
        if white_list:
            mask_white_item = df.get("品名", pd.Series([""]*len(df))).astype(str).str.upper().str.contains("|".join(white_list), na=False, regex=True)
            mask_white_vendor = df.get("仕入先名", pd.Series([""]*len(df))).astype(str).str.upper().str.contains("|".join(white_list), na=False, regex=True)
            suspicious_mask = suspicious_mask & ~(mask_white_item | mask_white_vendor)
            
        suspicious_df = df[suspicious_mask]
        if not suspicious_df.empty:
            print("\n[WARNING] 以下の伝票は金額ゼロまたは正味重量ゼロのため、除外すべきダミー伝票の可能性があります。")
            print("事務員様にて内容をご確認いただき、除外すべき場合はシステム(Supabase)の rule_master テーブルへ BLACK としてご登録ください。")
            print("正規の資源であり集計を通す場合は WHITE としてご登録ください。次回以降アラートが出なくなります。")
            for _, row in suspicious_df.iterrows():
                print(f"  - 仕入先: {row.get('仕入先名', '')}, 品名: {row.get('品名', '')}, 実重量: {row.get('実重量', 0)}kg, 金額: {row.get('金額', 0)}円")
            print("--------------------------------------------------------------------------------")


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
        for k, v in ITEM_CATEGORY_MAP.items():
            if k in item_str:
                return v
                
        weight = float(row.get("実重量", 0))
        is_adjustment = weight < 0 or any(kw in item_str for kw in ["値引", "調整", "相殺", "ﾃﾝﾋﾞｷ", "マイナス"])
        
        if is_adjustment:
            note_str = str(row.get("備考", ""))
            for k, v in ITEM_CATEGORY_MAP.items():
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
    import re
    def normalize_client_name(name: str) -> str:
        if not name: return ""
        name = name.translate(str.maketrans('Ａ-Ｚａ-ｚ０-９', 'A-Za-z0-9'))
        name = re.sub(r'\(株\)|㈱|株式会社|\(有\)|㈲|有限会社|\(同\)|合同会社', '', name)
        name = re.sub(r'[\s　]+', '', name)
        return name

    def map_supplier(sup: str, is_yokomochi: bool, category: str) -> str:
        if is_yokomochi or not sup: return sup
        if category == "⑤その他": return sup
        norm_sup = normalize_client_name(sup)
        if norm_sup in CLIENT_NAME_MAP:
            return CLIENT_NAME_MAP[norm_sup]
        # Fallback
        for mc in MAJOR_CLIENTS:
            if not mc: continue
            if normalize_client_name(mc) in norm_sup or norm_sup in normalize_client_name(mc):
                return mc
        return sup
    
    df_inbound["store_name"] = df_inbound["仕入先名"].fillna("").astype(str).str.strip()
    df_inbound["payee_name"] = df_inbound["支払先名"].fillna("").astype(str).str.strip()
    
    df_inbound["normalized_parent"] = df_inbound.apply(
        lambda r: str(r.get("支払先名", "")).strip() if str(r.get("支払先名", "")).strip() != "" else str(r.get("仕入先名", "")).strip(),
        axis=1
    )
    
    df_outbound["client_name"] = df_outbound["得意先名"].fillna("").astype(str).str.strip()
    df_outbound["spec_name"] = df_outbound["品名"].fillna("").astype(str).str.strip()
    

    # groupby 等で NaN により行が消滅するのを防ぐため、キーとなる列の NaN を空文字に置換
    fill_cols = ["支払先名", "仕入先名", "運送店名", "品名", "得意先名", "client_name", "spec_name", "normalized_parent"]
    for col in fill_cols:
        if col in df_inbound.columns:
            df_inbound[col] = df_inbound[col].fillna("")
        if col in df_outbound.columns:
            df_outbound[col] = df_outbound[col].fillna("")

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

def build_macro_report(df_inbound: pd.DataFrame, df_outbound: Optional[pd.DataFrame]=None, target_year: Optional[int]=None, target_month: Optional[int]=None) -> List[List[Any]]:
    grid: List[List[Any]] = []
    df_in = df_inbound.copy()
    if 'transaction_date' in df_in.columns:
        df_in['_date'] = pd.to_datetime(df_in['transaction_date'], errors='coerce')
        df_in['_ym'] = df_in['_date'].dt.to_period('M')
    else:
        df_in['_date'] = pd.NaT
        df_in['_ym'] = pd.NaT
    if target_year is None or target_month is None:
        target_year, target_month = (2026, 8)
        valid_dates = df_in['_date'].dropna()
        if not valid_dates.empty:
            mode_date = valid_dates.dt.to_period('M').mode()
            if not mode_date.empty:
                target_year, target_month = (int(mode_date.iloc[0].year), int(mode_date.iloc[0].month))
    target_period = pd.Period(f'{target_year:04d}-{target_month:02d}', freq='M')
    unique_yms = [target_period - 12 + i for i in range(13)]
    ym_to_col = {ym: i + 6 for i, ym in enumerate(unique_yms)}
    top_header: List[Any] = [None] * 20
    for ym, col_idx in ym_to_col.items():
        top_header[col_idx] = str(ym)
    top_header[19] = '前年同月差分'
    top_header[1] = '管理会社'
    top_header[2] = '客先名称'
    top_header[3] = '運送業者'
    top_header[4] = '品名'
    top_header[5] = '区分'
    grid.append(top_header)
    for cat_info in MASTER_HIERARCHY:
        cat_id = cat_info['cat_id']
        cat_disp = cat_info.get('cat_disp', cat_id)
        grid.append([cat_id] + [None] * 19)
        cat_totals = [0.0] * 14
        for route_info in cat_info['routes']:
            route_id = route_info['route_id']
            route_match_list = route_info['route_match']
            if cat_id == '＜参考＞事業所間横持ち':
                route_df = df_in[df_in['横持フラグ'] == True].copy()
            else:
                route_df = df_in[(df_in['大品目分類'] == cat_id) & df_in['経路分類'].isin(route_match_list) & (df_in['横持フラグ'] == False)].copy()
            if route_df.empty:
                continue
            grid.append([route_id, ''] + [None] * 18)
            route_totals = [0.0] * 14
            if not route_df.empty:
                if cat_id == '＜参考＞事業所間横持ち':
                    group_keys = ['仕入先名', '品名']
                else:
                    group_keys = ['normalized_parent', '仕入先名', '運送店名', '品名', '経路分類'] if 'normalized_parent' in route_df.columns else ['仕入先名', '運送店名', '品名', '経路分類']
                grouped = route_df.groupby(group_keys)
                for keys, supp_df in sorted(grouped):
                    row_data: List[Any] = [None] * 20
                    row_data[0] = ''
                    keys_tuple: Tuple[Any, ...] = keys if isinstance(keys, tuple) else (keys,)
                    if cat_id == '＜参考＞事業所間横持ち':
                        origin = str(keys_tuple[0]).replace('(横持)', '').replace('事業所', '').strip()
                        row_data[1] = f'{origin}→厚木'
                    else:
                        if len(group_keys) > 1:
                            disp_name = str(keys_tuple[1]).strip()
                            row_data[1] = disp_name if disp_name else str(keys_tuple[0]).strip()
                        else:
                            row_data[1] = str(keys_tuple[0]).strip()
                    ym_sums = supp_df.groupby('_ym')['実重量'].sum()
                    val_last_year = 0.0
                    val_this_month = 0.0
                    for ym_val, weight in ym_sums.items():
                        ym = cast(pd.Period, ym_val)
                        if ym in ym_to_col:
                            c_idx = ym_to_col[ym]
                            row_data[c_idx] = format_num(float(weight))
                            route_totals[c_idx - 6] += float(weight)
                            if ym == unique_yms[0]:
                                val_last_year = float(weight)
                            elif ym == unique_yms[12]:
                                val_this_month = float(weight)
                    diff = val_this_month - val_last_year
                    row_data[19] = format_num(diff)
                    route_totals[13] += diff
                    grid.append(row_data)
            subtotal: List[Any] = [None] * 20
            subtotal[0] = ''
            subtotal[0] = f"{route_id.split('.')[-1]}合計" if '.' in route_id else f'{route_id}合計'
            subtotal[1] = ''
            for i in range(13):
                if route_totals[i] > 0 or route_totals[i] < 0:
                    subtotal[i + 6] = format_num(route_totals[i])
            subtotal[19] = format_num(route_totals[13])
            grid.append(subtotal)
            for i in range(14):
                cat_totals[i] += route_totals[i]
        cat_subtotal: List[Any] = [None] * 20
        cat_subtotal[0] = ''
        cat_subtotal[0] = f'{cat_disp}合計'
        cat_subtotal[1] = ''
        for i in range(13):
            if cat_totals[i] != 0:
                cat_subtotal[i + 6] = format_num(cat_totals[i])
        cat_subtotal[19] = format_num(cat_totals[13])
        grid.append(cat_subtotal)
        grid.append([None] * 20)
    if df_outbound is not None and (not df_outbound.empty):
        df_out = df_outbound.copy()
        if 'transaction_date' in df_out.columns:
            df_out['_date'] = pd.to_datetime(df_out['transaction_date'], errors='coerce')
            df_out['_ym'] = df_out['_date'].dt.to_period('M')
        else:
            df_out['_date'] = pd.NaT
            df_out['_ym'] = pd.NaT
        grid.append(['＜出荷＞'] + [None] * 19)
        for cat_info in SHIPPING_HIERARCHY:
            cat_id = cat_info['cat_id']
            cat_disp = cat_info['cat_disp']
            grid.append([cat_id, ''] + [None] * 18)
            cat_shipping_totals = [0.0] * 14
            for route_info in cat_info['routes']:
                route_id = route_info['route_id']
                route_match_list = route_info['route_match']
                route_disp = route_info['route_disp']
                route_df = df_out[(df_out['大品目分類'] == cat_id) & df_out['経路分類'].isin(route_match_list)].copy()
                grid.append([route_id, ''] + [None] * 18)
                route_totals = [0.0] * 14
                if not route_df.empty:
                    group_keys = ['client_name', '得意先名', '運送店名(売上)', '品名', '取引区分名称(売上)'] if 'client_name' in route_df.columns else ['得意先名', '運送店名(売上)', '品名', '取引区分名称(売上)']
                    grouped = route_df.groupby(group_keys)
                    for keys, supp_df in sorted(grouped):
                        ship_row_data: List[Any] = [None] * 20
                        ship_row_data[0] = ''
                        keys_tuple = keys if isinstance(keys, tuple) else (keys,)
                        if len(group_keys) >= 4:
                            ship_row_data[1] = str(keys_tuple[0]).strip()
                            ship_row_data[2] = str(keys_tuple[1]).strip()
                            ship_row_data[3] = str(keys_tuple[2]).strip()
                            ship_row_data[4] = str(keys_tuple[3]).strip()
                            if len(group_keys) >= 5:
                                ship_row_data[5] = str(keys_tuple[4]).strip()
                        else:
                            ship_row_data[1] = str(keys_tuple[0]).strip()
                        ym_sums = supp_df.groupby('_ym')['実重量'].sum()
                        val_last_year = 0.0
                        val_this_month = 0.0
                        for ym_val, weight in ym_sums.items():
                            ym = cast(pd.Period, ym_val)
                            if ym in ym_to_col:
                                c_idx = ym_to_col[ym]
                                ship_row_data[c_idx] = format_num(float(weight))
                                route_totals[c_idx - 6] += float(weight)
                                if ym == unique_yms[0]:
                                    val_last_year = float(weight)
                                elif ym == unique_yms[12]:
                                    val_this_month = float(weight)
                        ship_row_data[19] = format_num(val_this_month - val_last_year)
                        route_totals[13] += val_this_month - val_last_year
                        grid.append(ship_row_data)
                ship_subtotal: List[Any] = [None] * 20
                ship_subtotal[0] = f'{route_disp}合計'
                ship_subtotal[1] = ''
                for i in range(13):
                    if route_totals[i] != 0:
                        ship_subtotal[i + 6] = format_num(route_totals[i])
                ship_subtotal[19] = format_num(route_totals[13])
                grid.append(ship_subtotal)
                for i in range(14):
                    cat_shipping_totals[i] += route_totals[i]
            cat_subtotal: List[Any] = [None] * 20
            cat_subtotal[0] = f'{cat_disp}出荷合計'
            cat_subtotal[1] = ''
            for i in range(13):
                if cat_shipping_totals[i] != 0:
                    cat_subtotal[i + 6] = format_num(cat_shipping_totals[i])
            cat_subtotal[19] = format_num(cat_shipping_totals[13])
            grid.append(cat_subtotal)
            grid.append([None] * 20)
    return grid



def _filter_month(df: pd.DataFrame, year: int, month: int) -> pd.DataFrame:
    df = df.copy()
    if "transaction_date" in df.columns:
        df["_date"] = pd.to_datetime(df["transaction_date"], errors="coerce")
        df["_year"] = df["_date"].dt.year
        df["_month"] = df["_date"].dt.month
        df["_day"] = df["_date"].dt.day
        return df[(df["_year"] == year) & (df["_month"] == month)].copy()
    return pd.DataFrame()

def build_micro_report(
    df_inbound: pd.DataFrame,
    df_outbound: Optional[pd.DataFrame] = None,
    target_year: Optional[int] = None,
    target_month: Optional[int] = None
) -> List[List[Any]]:
    if target_year is None or target_month is None:
        target_year, target_month = 2026, 8

    df_inbound_copy = df_inbound.copy()
    if "transaction_date" not in df_inbound_copy.columns and "年月日" in df_inbound_copy.columns:
        df_inbound_copy["transaction_date"] = df_inbound_copy["年月日"]

    df_in = _filter_month(df_inbound_copy, target_year, target_month)

    df_outbound_copy = df_outbound.copy() if df_outbound is not None else pd.DataFrame()
    if not df_outbound_copy.empty and "transaction_date" not in df_outbound_copy.columns and "年月日" in df_outbound_copy.columns:
        df_outbound_copy["transaction_date"] = df_outbound_copy["年月日"]
    df_out = _filter_month(df_outbound_copy, target_year, target_month) if not df_outbound_copy.empty else pd.DataFrame()

    def format_num(val):
        if pd.isna(val) or val == 0: return ""
        return f"{int(val):,}"

    grid = []
    headers = ["管理会社", "客先名称", "運送業者", "品名", "区分"] + [f"{i}日" for i in range(1, 32)] + ["合計"]
    grid.append(headers)

    if not df_in.empty:
        def normalize_for_compare(s: str) -> str:
            return str(s).strip().replace('㈲', '(有)').replace('㈱', '(株)')
        df_in['管理会社'] = df_in.apply(lambda r: '' if normalize_for_compare(r.get('normalized_parent','')) == normalize_for_compare(r.get('仕入先名','')) else str(r.get('normalized_parent','')).strip(), axis=1)
        df_in['客先名称'] = df_in.get('仕入先名', pd.Series(['']*len(df_in))).fillna('').astype(str).str.strip()
        df_in['運送業者'] = df_in.get('運送店名', pd.Series(['']*len(df_in))).fillna('').astype(str).str.strip()
        df_in['品名'] = df_in.get('品名', pd.Series(['']*len(df_in))).fillna('').astype(str).str.strip()
        df_in['区分'] = df_in.get('経路分類', pd.Series(['']*len(df_in))).fillna('').astype(str).str.strip()

        order_dai = ['①段ボール', '②新聞', '③雑誌', '④プラ類', '⑤その他', '⑥古布・繊維', '＜参考＞事業所間横持ち']
        daimoku_groups = dict(list(df_in.groupby('大品目分類')))
        
        grand_total_days = [0] * 31
        for daimoku in order_dai:
            if daimoku not in daimoku_groups: continue
            df_dai = daimoku_groups[daimoku]
            for keiro, df_keiro in df_dai.groupby('経路分類'):
                grid.append([f"{daimoku}-{keiro}"] + [""] * 36)
                df_gyousya = df_keiro.groupby(['管理会社', '客先名称', '運送業者', '品名', '区分'])
                for keys, df_g in df_gyousya:
                    kanri, kyakusaki, unso, hinmei, kubun = keys
                    days_val = [0] * 31
                    for _, r in df_g.iterrows():
                        d = r.get('_day')
                        if pd.notna(d) and 1 <= d <= 31:
                            days_val[int(d)-1] += r.get('実重量', 0)
                    total = sum(days_val)
                    if total > 0:
                        row = [kanri, kyakusaki, unso, hinmei, kubun] + [format_num(v) for v in days_val] + [format_num(total)]
                        grid.append(row)
                
                days_sub = [0] * 31
                for _, r in df_keiro.iterrows():
                    d = r.get('_day')
                    if pd.notna(d) and 1 <= d <= 31:
                        days_sub[int(d)-1] += r.get('実重量', 0)
                sub_total = sum(days_sub)
                grid.append(['', f"{keiro}合計", '', '', ''] + [format_num(v) for v in days_sub] + [format_num(sub_total)])
            
            days_dai = [0] * 31
            for _, r in df_dai.iterrows():
                d = r.get('_day')
                if pd.notna(d) and 1 <= d <= 31:
                    days_dai[int(d)-1] += r.get('実重量', 0)
                    grand_total_days[int(d)-1] += r.get('実重量', 0)
            dai_total = sum(days_dai)
            grid.append(['', f"{daimoku} 合計", '', '', ''] + [format_num(v) for v in days_dai] + [format_num(dai_total)])
            grid.append([''] * 37)
        
        grand_total = sum(grand_total_days)
        grid.append(['', "入荷総合計", '', '', ''] + [format_num(v) for v in grand_total_days] + [format_num(grand_total)])
        grid.append([''] * 37)

    grid.append(["＜出荷＞"] + [""] * 36)
    if not df_out.empty:
        df_out['管理会社'] = ''
        df_out['客先名称'] = df_out.get('client_name', pd.Series(['']*len(df_out))).fillna('').astype(str).str.strip()
        df_out['運送業者'] = ''
        df_out['品名'] = df_out.get('spec_name', pd.Series(['']*len(df_out))).fillna('').astype(str).str.strip()
        df_out['区分'] = df_out.get('経路分類', pd.Series(['']*len(df_out))).fillna('').astype(str).str.strip()

        order_dai = ['①段ボール', '②新聞', '③雑誌', '④プラ類', '⑤その他', '⑥古布・繊維', '＜参考＞事業所間横持ち']
        daimoku_groups = dict(list(df_out.groupby('大品目分類')))
        
        grand_total_days = [0] * 31
        for daimoku in order_dai:
            if daimoku not in daimoku_groups: continue
            df_dai = daimoku_groups[daimoku]
            for keiro, df_keiro in df_dai.groupby('経路分類'):
                grid.append([f"{daimoku}-{keiro}"] + [""] * 36)
                df_gyousya = df_keiro.groupby(['管理会社', '客先名称', '運送業者', '品名', '区分'])
                for keys, df_g in df_gyousya:
                    kanri, kyakusaki, unso, hinmei, kubun = keys
                    days_val = [0] * 31
                    for _, r in df_g.iterrows():
                        d = r.get('_day')
                        if pd.notna(d) and 1 <= d <= 31:
                            days_val[int(d)-1] += r.get('実重量', 0)
                    total = sum(days_val)
                    if total > 0:
                        row = [kanri, kyakusaki, unso, hinmei, kubun] + [format_num(v) for v in days_val] + [format_num(total)]
                        grid.append(row)
                
                days_sub = [0] * 31
                for _, r in df_keiro.iterrows():
                    d = r.get('_day')
                    if pd.notna(d) and 1 <= d <= 31:
                        days_sub[int(d)-1] += r.get('実重量', 0)
                sub_total = sum(days_sub)
                grid.append(['', f"{keiro}合計", '', '', ''] + [format_num(v) for v in days_sub] + [format_num(sub_total)])
            
            days_dai = [0] * 31
            for _, r in df_dai.iterrows():
                d = r.get('_day')
                if pd.notna(d) and 1 <= d <= 31:
                    days_dai[int(d)-1] += r.get('実重量', 0)
                    grand_total_days[int(d)-1] += r.get('実重量', 0)
            dai_total = sum(days_dai)
            grid.append(['', f"{daimoku} 合計", '', '', ''] + [format_num(v) for v in days_dai] + [format_num(dai_total)])
            grid.append([''] * 37)
        
        grand_total = sum(grand_total_days)
        grid.append(['', "出荷総合計", '', '', ''] + [format_num(v) for v in grand_total_days] + [format_num(grand_total)])

    return grid

def generate_warnings(df: pd.DataFrame) -> str:
    unknown_items = []
    for idx, row in df.iterrows():
        if row.get("大品目分類") == "⑤その他":
            item_str = str(row.get("品名", ""))
            is_mapped = False
            for k, v in ITEM_CATEGORY_MAP.items():
                if k in item_str and v == "⑤その他":
                    is_mapped = True
                    break
            if not is_mapped:
                note_str = str(row.get("備考", ""))
                for k, v in ITEM_CATEGORY_MAP.items():
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

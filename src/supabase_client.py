import os
import logging
from typing import Any, cast
import pandas as pd
from supabase import create_client, Client # type: ignore

logger = logging.getLogger(__name__)

from functools import lru_cache

@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("環境変数 SUPABASE_URL または SUPABASE_KEY が設定されていません。")
    return create_client(url, key)

def load_to_db(df: pd.DataFrame, source_file: str) -> None:
    client = get_supabase_client()
    
    # 冪等性: source_fileをキーに一括削除
    client.table("raw_nyuka_data").delete().eq("source_file", source_file).execute()
    
    df_copy = df.copy()
    df_copy["source_file"] = source_file
    
    # ホワイトリスト方式でスキーマ（有効な列名一覧）を動的に取得
    schema_res = client.table("raw_nyuka_data").select("*").limit(1).execute()
    if schema_res.data and isinstance(schema_res.data[0], dict):
        valid_columns = set(schema_res.data[0].keys())
    else:
        # データが存在しない場合のフォールバック（テーブル定義済みの想定カラムリスト）
        valid_columns = {
            "id", "created_at", "source_file", 
            "transaction_date", "仕入先コード", "仕入先名", "品名コード", "品名", 
            "経路", "車番", "正味重量", "調整重量", "数量", 
            "単価", "金額", "備考", "受付時間", "伝票番号",
            "支払先名", "運送店名", "自社他社区分", "得意先名", "取引区分", "デ区"
        }
        
    # CSVのヘッダーに含まれる全角・半角スペースを完全に除去
    df_copy.columns = df_copy.columns.str.replace(r'\s+', '', regex=True)
        
    # CSV内の「年月日」列をSupabase側の必須列である「transaction_date」にリネーム
    df_copy = df_copy.rename(columns={'年月日': 'transaction_date'})
        
    keep_cols = [col for col in df_copy.columns if str(col) in valid_columns]
    dropped_cols = [col for col in df_copy.columns if str(col) not in valid_columns]
    
    if dropped_cols:
        logger.info(f"DBに存在しない不要な列（ホワイトリスト外）を除外します: {dropped_cols}")
        
    df_copy = df_copy[keep_cols]
        
    import numpy as np
    # NaNをNoneに確実へ置換するため object 型へ変換してから replace (JSONシリアライズ対応)
    df_copy = df_copy.astype(object).replace({np.nan: None})
    
    records = df_copy.to_dict(orient="records")
    
    chunk_size = 1000
    for i in range(0, len(records), chunk_size):
        chunk = records[i:i + chunk_size]
        client.table("raw_nyuka_data").insert(cast(Any, chunk)).execute()
        
    logger.info(f"Supabaseへ {len(records)} 件のデータを保存しました ({source_file})")

def extract_from_db() -> pd.DataFrame:
    client = get_supabase_client()
    
    res = client.table("raw_nyuka_data").select("source_file").like("source_file", "%_completed").order("source_file", desc=True).limit(1).execute()
    if not res.data or not isinstance(res.data, list) or not isinstance(res.data[0], dict):
        return pd.DataFrame()
    latest_source = str(res.data[0].get("source_file", ""))
    
    data = []
    limit = 1000
    offset = 0
    while True:
        res = client.table("raw_nyuka_data").select("*").eq("source_file", latest_source).range(offset, offset + limit - 1).execute()
        if not res.data:
            break
        data.extend(res.data)
        if len(res.data) < limit:
            break
        offset += limit
        
    return pd.DataFrame(data)

def mark_as_completed(old_source: str, new_source: str) -> None:
    client = get_supabase_client()
    client.table("raw_nyuka_data").update({"source_file": new_source}).eq("source_file", old_source).execute()

def fetch_rule_master() -> dict[str, list[str]]:
    """
    Supabaseの rule_master テーブルからブラックリスト/ホワイトリストを取得する。
    戻り値: {"BLACK": ["キーワード1", ...], "WHITE": ["キーワード2", ...]}
    """
    client = get_supabase_client()
    try:
        res = client.table("rule_master").select("*").execute()
    except Exception as e:
        logger.warning(f"rule_master テーブルの取得に失敗しました（未作成の可能性があります）: {e}")
        return {"BLACK": [], "WHITE": []}
        
    rules: dict[str, list[str]] = {"BLACK": [], "WHITE": []}
    if res.data and isinstance(res.data, list):
        for row in res.data:
            if not isinstance(row, dict):
                continue
            rtype = str(row.get("rule_type", ""))
            kw = row.get("keyword")
            if rtype in rules and kw:
                # 表記揺れ吸収のため、大文字化・空白削除しておく
                import unicodedata
                norm_kw = unicodedata.normalize('NFKC', str(kw)).replace(" ", "").replace("　", "").upper()
                rules[rtype].append(norm_kw)
    return rules

import tempfile
import os

def download_template_from_storage(bucket_name: str, file_path: str) -> str:
    """
    Supabase Storageからテンプレートファイルを一時ディレクトリにダウンロードし、
    そのローカルパスを返す。
    """
    client = get_supabase_client()
    
    # テンポラリファイルを作成
    temp_fd, temp_path = tempfile.mkstemp(suffix=".xlsx")
    os.close(temp_fd)
    
    logger.info(f"Supabase Storage '{bucket_name}/{file_path}' からテンプレートをダウンロード中...")
    try:
        # Storageからバイナリデータを取得
        res = client.storage.from_(bucket_name).download(file_path)
        
        # ファイルに書き込み
        with open(temp_path, "wb") as f2:
            f2.write(res)
            
        logger.info(f"テンプレートをダウンロードしました: {temp_path}")
        return temp_path
    except Exception as e:
        logger.error(f"テンプレートのダウンロードに失敗しました: {e}")
        # フォールバックとして従来のローカルパスを返す
        fallback_path = os.path.join(os.path.dirname(__file__), "..", "Artifacts", "厚木事業所_入荷日報_search.xlsx")
        return fallback_path

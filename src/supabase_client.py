import os
import logging
from typing import Any, cast
import pandas as pd
from supabase import create_client, Client # type: ignore

logger = logging.getLogger(__name__)

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
    
    # NaNをNoneに置換 (JSONシリアライズ対応)
    df_copy = df_copy.where(pd.notnull(df_copy), None)
    
    records = df_copy.to_dict(orient="records")
    
    chunk_size = 1000
    for i in range(0, len(records), chunk_size):
        chunk = records[i:i + chunk_size]
        client.table("raw_nyuka_data").insert(cast(Any, chunk)).execute()
        
    logger.info(f"Supabaseへ {len(records)} 件のデータを保存しました ({source_file})")

def extract_from_db() -> pd.DataFrame:
    client = get_supabase_client()
    
    data = []
    limit = 1000
    offset = 0
    while True:
        res = client.table("raw_nyuka_data").select("*").range(offset, offset + limit - 1).execute()
        if not res.data:
            break
        data.extend(res.data)
        if len(res.data) < limit:
            break
        offset += limit
        
    return pd.DataFrame(data)

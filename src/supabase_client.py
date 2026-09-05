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
    
    # ホワイトリスト方式でスキーマ（有効な列名一覧）を動的に取得
    schema_res = client.table("raw_nyuka_data").select("*").limit(1).execute()
    if schema_res.data:
        valid_columns = set(schema_res.data[0].keys())
    else:
        # データが存在しない場合のフォールバック（テーブル定義済みの想定カラムリスト）
        valid_columns = {
            "id", "created_at", "source_file", 
            "transaction_date", "仕入先コード", "仕入先名", "品名コード", "品名", 
            "経路", "車番", "正味重量", "調整重量", "数量", 
            "単価", "金額", "備考", "受付時間", "伝票番号",
            "支払先名", "運送店名", "自社他社区分", "得意先名"
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

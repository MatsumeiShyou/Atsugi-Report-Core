import os
import logging
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

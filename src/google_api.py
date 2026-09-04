import os
import time
import random
import logging
from typing import Any, List, Callable
from functools import wraps
from datetime import datetime
from dateutil.relativedelta import relativedelta # type: ignore
from dotenv import load_dotenv # type: ignore

load_dotenv()

import pandas as pd
import google.auth # type: ignore
from googleapiclient.discovery import build # type: ignore
from googleapiclient.http import MediaIoBaseDownload # type: ignore
import gspread # type: ignore

logger = logging.getLogger(__name__)

# 指数バックオフのデコレータ
def exponential_backoff_with_jitter(max_retries: int = 5, base_delay: float = 1.0) -> Callable:
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            retries = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if retries >= max_retries:
                        logger.error(f"最大リトライ回数に達しました: {e}")
                        raise
                    sleep_time = base_delay * (2 ** retries) + random.uniform(0, 1)
                    logger.warning(f"APIエラー発生。{sleep_time:.2f}秒後にリトライします... ({retries + 1}/{max_retries})")
                    time.sleep(sleep_time)
                    retries += 1
        return wrapper
    return decorator

def get_credentials() -> Any:
    """環境に応じた認証情報を取得する（キーレス認証対応）"""
    scopes = [
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/spreadsheets"
    ]
    credentials, _ = google.auth.default(scopes=scopes)
    return credentials

@exponential_backoff_with_jitter(max_retries=3)
def fetch_csv_from_drive() -> List[pd.DataFrame]:
    """対象期間（13ヶ月分）のCSVをDriveから取得する"""
    folder_id = os.environ.get("TARGET_FOLDER_ID")
    if not folder_id:
        raise ValueError("環境変数 TARGET_FOLDER_ID が設定されていません。")

    creds = get_credentials()
    service = build("drive", "v3", credentials=creds)

    today = datetime.today()
    target_date = (today - relativedelta(months=13)).replace(day=1)
    target_date_str = target_date.strftime("%Y-%m-%dT00:00:00Z")

    query = f"'{folder_id}' in parents and modifiedTime >= '{target_date_str}' and trashed = false"
    
    logger.info(f"Drive API検索クエリ: {query}")
    results = service.files().list(
        q=query, 
        fields="files(id, name, mimeType)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute()
    
    items = results.get("files", [])
    logger.info(f"APIから取得した生のファイル件数: {len(items)}")
    for item in items:
        logger.info(f"取得ファイル - 名前: {item.get('name')}, MIMEタイプ: {item.get('mimeType')}")
        
    if len(items) == 0:
        logger.info("取得件数が0件のため、親フォルダへのアクセス可否をテストします...")
        try:
            folder_info = service.files().get(fileId='1-0bvWQDYrJEWZTglQ5R_zwgjazHUFhRO', supportsAllDrives=True).execute()
            logger.info(f"親フォルダ情報: {folder_info}")
        except Exception as e:
            logger.error(f"親フォルダへのアクセスに失敗しました: {e}")

    csv_items = [item for item in items if item.get('name', '').lower().endswith('.csv')]

    dataframes: List[pd.DataFrame] = []
    if not csv_items:
        logger.info("対象のCSVファイルは見つかりませんでした。")
        return dataframes

    import io
    for item in csv_items:
        file_id = item["id"]
        logger.info(f"ファイルダウンロード中: {item['name']}")
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        fh.seek(0)
        
        try:
            df = pd.read_csv(fh, encoding='cp932', thousands=',')
            dataframes.append(df)
        except Exception as e:
            logger.error(f"ファイル {item['name']} の読み込みに失敗しました: {e}")
            raise
            
    return dataframes

@exponential_backoff_with_jitter(max_retries=3)
def write_to_sheets(df: pd.DataFrame, sheet_name: str = "集計結果") -> None:
    """集計済みDataFrameをスプレッドシートに一括書き込みする"""
    spreadsheet_id = os.environ.get("TARGET_SPREADSHEET_ID")
    if not spreadsheet_id:
        raise ValueError("環境変数 TARGET_SPREADSHEET_ID が設定されていません。")

    creds = get_credentials()
    gc = gspread.authorize(creds)
    
    # JSONで書き込むため、NaNを空文字に置換
    df = df.fillna("")

    logger.info(f"スプレッドシート {spreadsheet_id} を開きます。")
    sh = gc.open_by_key(spreadsheet_id)
    
    try:
        wks = sh.worksheet(sheet_name)
    except Exception as e:
        if "WorksheetNotFound" in str(type(e).__name__):
            logger.info(f"シート '{sheet_name}' が見つからないため作成します。")
            wks = sh.add_worksheet(title=sheet_name, rows=1000, cols=20)
        else:
            raise

    # DataFrameのヘッダーとデータをリスト形式に変換
    data = [df.columns.values.tolist()] + df.values.tolist()
    
    logger.info(f"シート '{sheet_name}' に {len(data)} 行書き込みます...")
    wks.clear()
    wks.update(values=data, range_name="A1")
    logger.info("書き込みが完了しました。")

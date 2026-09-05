import os
import logging
import pandas as pd
from dotenv import load_dotenv

from google_api import fetch_csv_from_drive, write_to_sheets
from supabase_client import load_to_db, extract_from_db
from aggregate_report import transform_raw_data, build_macro_report, build_micro_report

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main() -> None:
    logger.info("ETL パイプラインを開始します。")

    folder_id = os.environ.get("FOLDER_ID")
    if folder_id:
        os.environ["TARGET_FOLDER_ID"] = folder_id

    # [E] Extract
    logger.info("DriveからCSVを取得します...")
    dataframes = fetch_csv_from_drive()
    if not dataframes:
        raise ValueError("Google Driveから対象のCSVデータが1件も取得できませんでした。")

    # [L] Load to DB (raw_nyuka_data)
    logger.info("Supabaseへ生データを保存します...")
    combined_raw = pd.concat(dataframes, ignore_index=True)
    if "source_file" not in combined_raw.columns:
        combined_raw["source_file"] = "drive_import_13months.csv"
        
    load_to_db(combined_raw, source_file="drive_import_13months.csv")

    # [T] Transform
    logger.info("Supabaseからデータを抽出し、変換処理を行います...")
    raw_df = extract_from_db()
        
    transformed_df = transform_raw_data(raw_df)
    
    macro_grid = build_macro_report(transformed_df)
    micro_grid = build_micro_report(transformed_df)

    macro_df = pd.DataFrame(macro_grid)
    micro_df = pd.DataFrame(micro_grid)

    # [L] Load to Sheets
    logger.info("整形済みデータをスプレッドシートへ出力します...")
    # 8-5計は A列(1) から出力（属性テキストを含むため）
    write_to_sheets(macro_df, sheet_name="8-5計", start_col=1)
    # 8-5 は A列(1) から出力（属性テキストを含むため）
    write_to_sheets(micro_df, sheet_name="8-5", start_col=1)

    logger.info("ETL パイプラインが完了しました。")

if __name__ == "__main__":
    main()

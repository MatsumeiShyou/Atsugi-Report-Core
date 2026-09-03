import os
import logging
import pandas as pd
from dotenv import load_dotenv

from google_api import fetch_csv_from_drive, write_to_sheets
from aggregate_report import process_dataframe

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main() -> None:
    logger.info("Atsugi Report Core 最終結合処理を開始します。")

    # 環境変数からFOLDER_IDとTARGET_SPREADSHEET_IDを取得
    folder_id = os.environ.get("FOLDER_ID")
    spreadsheet_id = os.environ.get("TARGET_SPREADSHEET_ID")

    if folder_id:
        os.environ["TARGET_FOLDER_ID"] = folder_id # google_api.py の内部参照用にセット
    if spreadsheet_id:
        os.environ["TARGET_SPREADSHEET_ID"] = spreadsheet_id

    # 1. DriveからCSVを取得して結合
    logger.info("DriveからCSVファイルを取得・結合します。")
    dataframes = fetch_csv_from_drive()
    if not dataframes:
        logger.warning("処理対象のデータがありませんでした。処理を終了します。")
        return

    raw_df = pd.concat(dataframes, ignore_index=True)
    logger.info(f"合計 {len(raw_df)} 行のデータを読み込みました。")

    # 2. データの集計・加工
    logger.info("データの集計・加工を開始します。")
    processed_df = process_dataframe(raw_df)

    # 3. 出力フォーマットの整形
    logger.info("出力フォーマットを整形します。")
    # 1列目: 仕入先名、2列目: 空白（「⑤その他」の場合のみ元の品名）、重量はkgのまま
    
    supplier_col = "集計用仕入先名" if "集計用仕入先名" in processed_df.columns else "仕入先名"
    
    output_rows = []
    for _, row in processed_df.iterrows():
        supplier = row.get(supplier_col, "")
        category = row.get("大品目分類", "")
        original_item = row.get("元品名", "")
        
        # 2列目処理: 「⑤その他」の場合のみ元の品名を格納
        col2 = original_item if category == "⑤その他" else ""
        
        output_rows.append({
            "仕入先名": supplier,
            "品名詳細": col2,
            "大品目分類": category,
            "経路分類": row.get("経路分類", ""),
            "状態分類": row.get("状態分類", ""),
            "重量(kg)": row.get("実重量", 0.0)
        })

    output_df = pd.DataFrame(output_rows)

    # 4. Sheetsへ書き込み
    logger.info("スプレッドシートへバッチ更新で一括書き込みを行います。")
    write_to_sheets(output_df)
    logger.info("全ての処理が完了しました。")

if __name__ == "__main__":
    main()

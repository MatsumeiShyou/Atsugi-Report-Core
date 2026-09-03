import json

MAJOR_CLIENTS = [
    "タチオカ商会", "青木商店", "IWD", "カナキン", "浅見運輸倉庫", "ダイコー商事",
    "旭満", "対馬商店", "アオイ", "湘南（上田商店）", "湘南リユース", "中央カンセー",
    "サンクリーン", "神奈中商事", "関東ダイレクトサービス", "共栄商社", "ティーエスエンバイロ",
    "厚木市資源再生センター", "厚木資源再生センター", "アイダスト", "クリーンサービス",
    "アクト・エア", "北湘ヴィークル", "セクメット", "清水商店", "旭商会", "未竜運輸",
    "坂田亮作商店", "JSRネット（富士通関連）", "ｸﾘｰﾝｻｰﾋﾞｽ（ﾀｷﾛﾝほか）", "山櫻",
    "コトブキパック", "ニッポンロジ株式会社", "ﾎﾟｼﾞﾃｨﾌﾞ（富士ﾛｼﾞ関連）", "DSP（ピアノ運送ほか）",
    "DSP", "田丸（エスポットほか）", "田丸", "アークル", "アート引越センター", "アオイ（富士電線）",
    "ナカダイ（東京冷機ほか）", "丸紅（不二家）", "高山常温一括センター", "高山一括センター",
    "大本紙料（クリエイトほか）", "大本紙料", "共栄商社（ストリックスほか）", "TS環境リサイクル",
    "大創産業 神奈川RDC", "紙商", "中村伸行", "毎日新聞秦野", "平塚環興", "キョウセイ環境",
    "三星産業", "ｴｺｻﾎﾟｰﾄ（ﾊﾟﾙｼｽﾃﾑ）", "湘南リンテック加工", "東部サービスセンター",
    "リンテック", "三善製紙", "ユーネット", "吉田印刷", "パスコ", "そのた"
]
CATEGORIES = ["①段ボール", "②新聞", "③雑誌", "④プラ類", "⑤その他"]
ROUTES = ["自社回収", "他社回収", "持込み"]
YOKOMOCHI_KEYWORDS = ["富士", "浜松", "御殿場", "(横持)"]

macro_map = {}
r = 1
for cat in CATEGORIES:
    for route in ROUTES:
        for client in MAJOR_CLIENTS[:11]:
            macro_map[f"{cat}_{route}_{client}"] = r
            r += 1

r = 172
for kw in YOKOMOCHI_KEYWORDS:
    macro_map[f"横持品_{kw}"] = r
    r += 1

micro_map = {}
r = 1
for client in MAJOR_CLIENTS:
    for cat in CATEGORIES:
        for route in ROUTES:
            if r <= 875:
                micro_map[f"{client}_{cat}_{route}"] = r
                r += 1

with open("src/mapping_definitions.py", "w", encoding="utf-8") as f:
    f.write('from typing import Dict\n\n')
    f.write('YOKOMOCHI_KEYWORDS = ' + repr(YOKOMOCHI_KEYWORDS) + '\n')
    f.write('MAJOR_CLIENTS = set(' + repr(MAJOR_CLIENTS) + ')\n')
    f.write('ITEM_TO_CATEGORY = {"段ボール": "①段ボール", "新聞": "②新聞", "雑誌": "③雑誌", "PETボトル": "④プラ類", "その他": "⑤その他"}\n\n')
    f.write('MACRO_ROW_MAP: Dict[str, int] = ' + json.dumps(macro_map, ensure_ascii=False, indent=4) + '\n\n')
    f.write('MICRO_ROW_MAP: Dict[str, int] = ' + json.dumps(micro_map, ensure_ascii=False, indent=4) + '\n')

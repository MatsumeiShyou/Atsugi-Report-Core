#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
alternative_gate.py — 「引き算の代替案」ゲート（PreToolUse）

目的:
  依存の追加 / src/ への新規ファイル追加 を検知し、
  DECISIONS.md に「その対象を scope に含む、承認済みの決定」が無ければ
  ツール実行を中断する。既定値を「何も足さない」に寄せるための足止め。

使い方:
  - フック経由: stdin に PreToolUse の JSON ペイロードを渡す
  - 手動確認 : python .agent/scripts/alternative_gate.py --path src/report/new.py

終了コード:
  0 = 許可 / 1 = 中断（ブロック）/ 0 = 判定対象外

バイパス:
  環境変数 AG_GATE_BYPASS に理由を入れて実行（ログに残る）
  例: AG_GATE_BYPASS="ADR-012で人間承認済み" <command>

限界（重要）:
  DECISIONS.md はエージェント自身も書ける。これは「忘れ防止」と「記録の強制」で
  あって、偽造対策ではない。偽造まで防ぎたい場合は STRICT_COMMITTED=True にして
  「コミット済みの決定のみ有効」とするか、ツール側の承認ダイアログを併用すること。
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ----------------------------------------------------------------------
# 設定
# ----------------------------------------------------------------------
SRC_DIRS = ("src",)                 # 新規ファイルを監視するディレクトリ
SRC_SUFFIXES = (".py",)             # 監視する拡張子
DEP_FILES = {                       # 依存定義ファイル（basename で判定）
    "requirements.txt", "requirements-dev.txt", "constraints.txt",
    "pyproject.toml", "poetry.lock", "Pipfile", "Pipfile.lock",
    "setup.py", "setup.cfg", "uv.lock",
}
DECISIONS_FILE = "DECISIONS.md"
LOG_FILE = ".agent/logs/gate.jsonl"
REQUIRED_FIELDS = ("choice", "scope", "alternative", "reason", "approved-by")
STRICT_COMMITTED = False            # True: git HEAD にコミット済みの決定のみ有効とみなす

# ----------------------------------------------------------------------
# 出力（Windows コンソールでも落ちないように）
# ----------------------------------------------------------------------
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


# ----------------------------------------------------------------------
# リポジトリルート解決
# ----------------------------------------------------------------------
def find_root(start: Path) -> Path:
    for d in [start, *start.parents]:
        if (d / "AGENTS.md").exists() or (d / ".git").exists():
            return d
    return start


# ----------------------------------------------------------------------
# ペイロードから対象パスを抽出
# ----------------------------------------------------------------------
PATH_KEYS = {
    "path", "file_path", "filepath", "target_file", "targetfile",
    "abs_path", "absolute_path", "filename", "file", "uri", "notebook_path",
    "new_file_path", "relative_path",
}


def collect_paths(obj, out: list) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and k.lower() in PATH_KEYS:
                out.append(v)
            else:
                collect_paths(v, out)
    elif isinstance(obj, list):
        for v in obj:
            collect_paths(v, out)


def normalize(raw: str, root: Path) -> str | None:
    """絶対/相対/file:// を root 相対の posix パスに正規化。root 外は None。"""
    s = raw.strip().strip('"').strip("'")
    if not s:
        return None
    if s.startswith("file://"):
        s = s[7:]
        if re.match(r"^/[A-Za-z]:", s):  # file:///c:/... 対策
            s = s[1:]
    p = Path(os.path.expandvars(os.path.expanduser(s)))
    if not p.is_absolute():
        p = root / p
    try:
        rel = os.path.relpath(p.resolve(strict=False), root.resolve(strict=False))
    except Exception:
        return None
    rel = rel.replace(os.sep, "/")
    if rel.startswith("../"):
        return None
    return rel


def classify(rel: str, root: Path) -> str | None:
    """判定対象なら trigger 名を返す。対象外は None。"""
    name = rel.rsplit("/", 1)[-1]
    if name in DEP_FILES:
        return "dependency"
    if rel.startswith(tuple(d + "/" for d in SRC_DIRS)) and rel.endswith(SRC_SUFFIXES):
        if not (root / rel).exists():          # まだ存在しない = 新規ファイル
            return "new_src_file"
    return None


# ----------------------------------------------------------------------
# DECISIONS.md のパース
# ----------------------------------------------------------------------
HEADER_RE = re.compile(r"^##\s+(?P<id>[A-Za-z]+-\d+)\s*(?P<title>.*)$")
FIELD_RE = re.compile(r"^\s*[-*]\s*(?P<key>[A-Za-z-]+)\s*:\s*(?P<val>.*?)\s*$")


def parse_decisions(text: str) -> list:
    entries, cur = [], None
    for line in text.splitlines():
        m = HEADER_RE.match(line)
        if m:
            cur = {"id": m.group("id"), "title": m.group("title").strip(), "fields": {}}
            entries.append(cur)
            continue
        if cur is None:
            continue
        f = FIELD_RE.match(line)
        if f:
            val = re.split(r"\s+#", f.group("val"))[0].strip()  # 行末コメントを除去
            cur["fields"][f.group("key").lower()] = val
    return entries


def read_decisions(root: Path) -> list:
    if STRICT_COMMITTED:
        try:
            out = subprocess.run(
                ["git", "show", f"HEAD:{DECISIONS_FILE}"],
                cwd=root, capture_output=True, text=True, encoding="utf-8",
            )
            return parse_decisions(out.stdout) if out.returncode == 0 else []
        except Exception:
            return []
    p = root / DECISIONS_FILE
    if not p.exists():
        return []
    return parse_decisions(p.read_text(encoding="utf-8", errors="replace"))


def is_valid(entry: dict) -> bool:
    f = entry["fields"]
    if not all(k in f and f[k] for k in REQUIRED_FIELDS):
        return False
    if f["choice"].strip().upper() not in ("A", "B"):
        return False
    return f["approved-by"].strip().lower().startswith("human")


def scope_tokens(entry: dict) -> list:
    raw = entry["fields"].get("scope", "")
    return [t.strip().replace("\\", "/") for t in re.split(r"[,\s]+", raw) if t.strip()]


def match_scope(rel: str, entry: dict) -> bool:
    for tok in scope_tokens(entry):
        if tok == rel:
            return True
        if tok.endswith("/") and rel.startswith(tok):
            return True
        if any(c in tok for c in "*?[") and fnmatch.fnmatch(rel, tok):
            return True
    return False


def find_decision(rel: str, entries: list):
    for e in entries:
        if is_valid(e) and match_scope(rel, e):
            return e
    return None


# ----------------------------------------------------------------------
# ログ
# ----------------------------------------------------------------------
def log(root: Path, record: dict) -> None:
    try:
        p = root / LOG_FILE
        p.parent.mkdir(parents=True, exist_ok=True)
        record["ts"] = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass  # ログ失敗でゲートを壊さない


# ----------------------------------------------------------------------
# ブロックメッセージ
# ----------------------------------------------------------------------
def block_message(hits: list, next_id: str) -> str:
    targets = "\n".join(f"  - [{kind}] {rel}" for kind, rel in hits)
    scope = ", ".join(rel for _, rel in hits)
    return f"""
[GATE BLOCK] 引き算の代替案が未記録です。

対象:
{targets}

この変更は「足す」変更です。実装前に次を人間に提示し、A/B の選択を得てください。
  [State]       現状と課題
  [Decision]    要求どおりの案（対象ファイル / 追加する依存）
  [Alternative] 何も足さない案 / 既存の流用・統合案（無ければ「無し」と理由）
  [Reason]      技術的根拠
  [Risk]        副作用と回避策

選択後、DECISIONS.md に以下を追記すれば本ゲートは通過します（1機能につき1エントリ）。

## {next_id} {datetime.now().strftime('%Y-%m-%d')} <機能名>
- choice: A            # A=要求どおり / B=代替案
- scope: {scope}
- alternative: <何も足さない案の内容。無ければ「無し」と理由>
- reason: <その選択の理由>
- approved-by: human

バイパスが必要な場合: AG_GATE_BYPASS="<理由>" を付けて再実行（ログに残ります）
""".rstrip()


def next_decision_id(entries: list) -> str:
    nums = [int(re.sub(r"\D", "", e["id"]) or 0) for e in entries] or [0]
    return f"AG-{max(nums) + 1:04d}"


# ----------------------------------------------------------------------
# main
# ----------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="引き算の代替案ゲート（PreToolUse）")
    ap.add_argument("--path", action="append", default=[], help="判定するパス（複数可）")
    ap.add_argument("--root", default=None, help="リポジトリルート")
    ap.add_argument("--quiet", action="store_true", help="許可時は何も出力しない")
    args = ap.parse_args()

    root = Path(args.root) if args.root else find_root(Path.cwd())

    raw_paths: list = list(args.path)
    if not sys.stdin.isatty():
        data = sys.stdin.read()
        if data.strip():
            try:
                collect_paths(json.loads(data), raw_paths)
            except json.JSONDecodeError:
                raw_paths.extend(re.findall(r"[\w./\\:-]+\.(?:py|txt|toml|cfg|lock)", data))

    hits, seen = [], set()
    for raw in raw_paths:
        rel = normalize(raw, root)
        if not rel or rel in seen:
            continue
        seen.add(rel)
        kind = classify(rel, root)
        if kind:
            hits.append((kind, rel))

    if not hits:
        return 0  # 判定対象外（通常の編集など）

    bypass = os.environ.get("AG_GATE_BYPASS", "").strip()
    if bypass:
        log(root, {"event": "bypass", "targets": [h[1] for h in hits], "reason": bypass})
        eprint(f"[GATE BYPASS] {bypass} — 対象: {', '.join(h[1] for h in hits)}")
        return 0

    entries = read_decisions(root)
    missing = [(k, r) for k, r in hits if find_decision(r, entries) is None]

    if missing:
        log(root, {"event": "block", "targets": [r for _, r in missing],
                   "triggers": sorted({k for k, _ in missing})})
        eprint(block_message(missing, next_decision_id(entries)))
        return 1

    matched = {r: find_decision(r, entries)["id"] for _, r in hits}
    log(root, {"event": "allow", "targets": list(matched), "decisions": matched})
    if not args.quiet:
        eprint("[GATE PASS] " + ", ".join(f"{r} -> {d}" for r, d in matched.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())

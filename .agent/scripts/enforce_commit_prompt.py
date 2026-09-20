import sys, json, subprocess, os

def main():
    try:
        data = json.loads(sys.stdin.read())
    except Exception:
        print("{}")
        return

    # Check git status
    try:
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=os.path.dirname(os.path.abspath(__file__)) + "/../../")
        if not status.stdout.strip():
            print("{}")
            return
    except Exception:
        print("{}")
        return

    # Uncommitted changes exist. Check transcript
    transcript_path = data.get("transcriptPath")
    asked = False
    if transcript_path and os.path.exists(transcript_path):
        try:
            with open(transcript_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                for line in reversed(lines[-20:]):
                    step = json.loads(line)
                    if step.get("source") == "MODEL" and step.get("type") == "PLANNER_RESPONSE":
                        content = step.get("content", "")
                        if "コミット" in content or "commit" in content or "push" in content.lower() or "プッシュ" in content:
                            asked = True
                        break
        except Exception:
            pass

    if asked:
        print("{}")
        return

    print(json.dumps({
        "decision": "continue",
        "reason": "[GATE BLOCK] 未コミットの変更が残っています。終了する前に、必ずユーザーに『変更をコミットしてPushしますか？』と質問してください。"
    }))

if __name__ == "__main__":
    main()

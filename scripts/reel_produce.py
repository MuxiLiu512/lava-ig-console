#!/usr/bin/env python3
"""Reels 混合式量產：一支片由多種段落組成，不是從頭到尾口播。

為什麼是混合式〔Jesse 2026-08-27，看完 breeze 與業配片後〕：
  breeze 那支不是一鏡到底的口播——手持實拍、App 畫面閃過一秒、酒吧空景、真人笑，
  剪在一起才有真實感。morning.jason 也是談話頭與剪紙動畫交錯。
  純口播既單調又貴。

成本才是真正的設計約束（2026-08-26 實測單價）：
  seedance_2_5  1080p + 語音   9    點/秒   ← 口播只能用這個
  seedance_2_5  720p  無語音   6.5  點/秒   ← 空景用這個就夠
  gpt_image_2   分鏡一張       7    點
  soul_2        角色一張       0.12 點      ← 角色重用，幾乎免費
  自有素材／字卡                0    點

  30 秒全口播 = 270 點。
  30 秒混合（8 秒口播 + 10 秒空景 + 12 秒自有素材／字卡）= 72 + 65 + 0 = 137 點。
  同樣長度，成本少一半，而且更好看。

prompt 全部來自 config/reel-prompts.md，不寫死在這裡——
那份檔案是 iterate_harness 依 Jesse 退回意見累積規則的地方（與貼文的 style-notes 同一套）。

用法：
  python3 scripts/reel_produce.py --spec data/reels/<name>.json          # 只估成本，不生成
  python3 scripts/reel_produce.py --spec ... --go                        # 真的生成
"""
import os, sys, json, argparse, importlib.util, datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("sc", os.path.join(_HERE, "sync_console.py"))
SC = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(SC)
REPO = SC.REPO

# 實測單價（2026-08-26，transactions 對帳）。改單價只改這裡。
RATE = {
    "talk_per_sec":  9.0,     # seedance_2_5 1080p + generate_audio
    "broll_per_sec": 6.5,     # seedance_2_5 720p 無語音
    "board":         7.0,     # gpt_image_2 21:9 2k high
    "character":     0.12,    # soul_2 3:4 2k
}
SEG_TYPES = ("talk", "broll", "own", "cards")


def estimate(spec):
    """回傳 (逐段明細, 總點數)。這是不可逆花費前的那道人閘——先看清楚再決定。"""
    rows, total = [], 0.0
    cast_exists = os.path.exists(os.path.join(SC.DATA, "reels_cast.json"))
    for i, s in enumerate(spec.get("segments", []), 1):
        t = s.get("type")
        sec = float(s.get("seconds") or 0)
        if t == "talk":
            c = sec * RATE["talk_per_sec"] + RATE["board"]
            if not cast_exists and i == 1:
                c += RATE["character"]
            model = "seedance_2_5 1080p+語音 ＋ gpt_image_2 分鏡"
        elif t == "broll":
            c = sec * RATE["broll_per_sec"]
            model = "seedance_2_5 720p 無語音"
        elif t == "own":
            c, model = 0.0, "自有素材（零成本）"
        elif t == "cards":
            c, model = 0.0, "render_reel.py 字卡（零成本）"
        else:
            raise SystemExit("✗ 第 %d 段的 type 不認得：%r（可用：%s）" % (i, t, "／".join(SEG_TYPES)))
        rows.append({"n": i, "type": t, "seconds": sec, "credits": round(c, 2),
                     "model": model, "note": (s.get("note") or "")[:40]})
        total += c
    return rows, round(total, 2)


def report(spec, rows, total):
    secs = sum(r["seconds"] for r in rows)
    print("《%s》%.0f 秒、%d 段\n" % (spec.get("title", "未命名"), secs, len(rows)))
    print("  段 類型     秒   點數  模型")
    for r in rows:
        print("  %2d %-6s %4.0f %6.1f  %s" % (r["n"], r["type"], r["seconds"], r["credits"], r["model"]))
    print("\n  合計 %.1f 點" % total)
    allsec = secs * RATE["talk_per_sec"] + RATE["board"]
    if total < allsec:
        print("  （同長度全口播要 %.0f 點，混合省下 %.0f 點 / %.0f%%）"
              % (allsec, allsec - total, 100 * (1 - total / allsec)))
    print("\n  單價：口播 %.1f 點/秒、空景 %.1f 點/秒、分鏡 %.0f 點/張、角色 %.2f 點/張"
          % (RATE["talk_per_sec"], RATE["broll_per_sec"], RATE["board"], RATE["character"]))


def log_production(spec, rows, total, jobs=None):
    """把每次生成記進 data/reels.json：用了哪些模型、花多少、哪個 prompt 版本。
    沒有這份紀錄就無法回答「這次比上次好在哪、貴在哪」。"""
    fp = "reels.json"
    try:
        doc = SC.load(fp)
    except FileNotFoundError:
        doc = {"note": "Reels 生產紀錄：每次生成的段落、模型、成本與 prompt 版本。", "reels": []}
    prompts_fp = os.path.join(REPO, "config", "reel-prompts.md")
    ver = ""
    if os.path.exists(prompts_fp):
        import hashlib
        ver = hashlib.md5(open(prompts_fp, "rb").read()).hexdigest()[:8]
    doc.setdefault("reels", []).append({
        "id": spec.get("id") or spec.get("title", "reel"),
        "title": spec.get("title", ""),
        "ts": SC._now_iso(),
        "seconds": sum(r["seconds"] for r in rows),
        "credits": total,
        "segments": rows,
        "prompt_version": ver,          # config/reel-prompts.md 的指紋，改過就知道
        "jobs": jobs or [],
        "status": "generated" if jobs else "estimated",
    })
    SC.save(fp, doc)
    print("\n已記錄到 data/reels.json（prompt 版本 %s）" % ver)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--go", action="store_true", help="真的生成（預設只估成本）")
    a = ap.parse_args()
    p = a.spec if os.path.isabs(a.spec) else os.path.join(REPO, a.spec)
    with open(p, encoding="utf-8") as f:
        spec = json.load(f)
    rows, total = estimate(spec)
    report(spec, rows, total)
    if not a.go:
        print("\n這是估算，還沒花任何點數。確認後加 --go。")
        log_production(spec, rows, total)
        return
    print("\n生成需要由對話端呼叫 Higgsfield（MCP 工具不在本腳本內）。")
    print("本腳本負責：估成本、記錄模型與版本、產出段落清單供對話端逐段執行。")
    print(json.dumps({"segments": spec.get("segments", []), "estimate": total},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

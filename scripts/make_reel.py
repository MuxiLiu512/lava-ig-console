#!/usr/bin/env python3
"""Reels 探針：把已完成的輪播成品轉成 9:16 短影音。

存在的理由（2026-08-13 Jesse 決策）：
  2026 年 IG 的分發主力是短影音，用輪播追 10 倍觸及是在載體選擇上先輸一半。
  而且載體差異（2 到 5 倍）是唯一效果量大到在 n=36 樣本內測得出來的變數，
  內容微調（10% 到 20%）在這個樣本數下永遠測不出來。
  成本只有這支腳本：成品 PNG 已存在，ffmpeg 已是 forager 的依賴。

做法：不重新排版。輪播成品是 4:5（1079×1350），Reels 是 9:16（1080×1920），
  上下差的 570px 用「同一張圖放大模糊」填滿，中央疊原圖。
  這是社群通行做法，且保證文字區完全不被裁切。

停留時間依角色分配（封面要留住人，CTA 要看得完）：
  封面 3.5s／內容 2.6s／CTA 3.0s，九張約 25 秒，落在 Reels 完播甜蜜點。

用法：
  python3 scripts/make_reel.py <post-id>            # 產出 docs/reels/<post-id>.mp4
  python3 scripts/make_reel.py <post-id> --open     # 產完直接開啟
  python3 scripts/make_reel.py --all-approved       # 所有 approved/scheduled 都產
"""
import os, sys, json, glob, re, subprocess, tempfile, shutil, argparse

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
FFMPEG = "/opt/homebrew/bin/ffmpeg"
OUT_DIR = os.path.join(REPO, "docs", "reels")
W, H = 1080, 1920          # Reels 規格
FPS = 30
DUR_COVER, DUR_BODY, DUR_CTA = 3.5, 2.6, 3.0
XFADE = 0.35               # 轉場秒數


def _dur_for(idx, total):
    if idx == 1:
        return DUR_COVER
    if idx == total:
        return DUR_CTA
    return DUR_BODY


def build_frame(src, dst):
    """單張 4:5 → 9:16：背景是同圖放大模糊，中央疊原圖滿寬。"""
    vf = (
        # 背景：填滿 1080x1920 後裁切，重模糊並壓暗
        "[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
        "crop={W}:{H},boxblur=40:2,eq=brightness=-0.22:saturation=0.6[bg];"
        # 前景：等比縮到滿寬
        "[0:v]scale={W}:-1[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2"
    ).format(W=W, H=H)
    r = subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", src,
                        "-filter_complex", vf, "-frames:v", "1", dst],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("build_frame 失敗：%s" % (r.stderr or "")[-200:])


def make_reel(pid, open_after=False):
    fin = os.path.join(REPO, "docs", "finals", pid)
    imgs = sorted(glob.glob(os.path.join(fin, "slide-*.jpg")),
                  key=lambda f: int(re.search(r"slide-(\d+)", f).group(1)))
    if len(imgs) < 3:
        print("⏭ %s：成品不足 3 張" % pid[:28]); return None

    work = tempfile.mkdtemp(prefix="reel-", dir="/private/tmp")
    try:
        frames = []
        for i, src in enumerate(imgs, 1):
            dst = os.path.join(work, "f%02d.png" % i)
            build_frame(src, dst)
            frames.append((dst, _dur_for(i, len(imgs))))

        # 每張先各自成段，再用 xfade 串接（xfade 需要等長的輸入串流）
        segs = []
        for i, (f, d) in enumerate(frames):
            seg = os.path.join(work, "s%02d.mp4" % i)
            subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-loop", "1", "-i", f,
                            "-t", str(d), "-r", str(FPS),
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", seg],
                           check=True, capture_output=True)
            segs.append((seg, d))

        inputs, filt, prev, offset = [], [], None, 0.0
        for i, (seg, d) in enumerate(segs):
            inputs += ["-i", seg]
            if i == 0:
                prev, offset = "0:v", d - XFADE
                continue
            out = "x%d" % i
            filt.append("[%s][%d:v]xfade=transition=fade:duration=%s:offset=%s[%s]"
                        % (prev, i, XFADE, round(offset, 3), out))
            prev = out
            offset += d - XFADE

        os.makedirs(OUT_DIR, exist_ok=True)
        out_mp4 = os.path.join(OUT_DIR, pid + ".mp4")
        cmd = [FFMPEG, "-y", "-loglevel", "error"] + inputs
        if filt:
            cmd += ["-filter_complex", ";".join(filt), "-map", "[%s]" % prev]
        cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "20",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-r", str(FPS), out_mp4]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print("✗ %s 合成失敗：%s" % (pid[:26], (r.stderr or "")[-240:])); return None

        total = sum(d for _, d in frames) - XFADE * (len(frames) - 1)
        size_mb = os.path.getsize(out_mp4) / 1e6
        print("✓ %-28s %d 張 → %.1f 秒 %.1fMB" % (pid[:28], len(imgs), total, size_mb))
        if open_after:
            subprocess.run(["open", out_mp4])
        return out_mp4
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("post_id", nargs="?")
    ap.add_argument("--all-approved", action="store_true")
    ap.add_argument("--open", action="store_true")
    a = ap.parse_args()

    if a.all_approved:
        d = json.load(open(os.path.join(REPO, "data", "posts.json"), encoding="utf-8"))
        targets = [p["id"] for p in d["posts"] if p.get("status") in ("approved", "scheduled")]
    elif a.post_id:
        targets = [a.post_id]
    else:
        ap.error("要給 post-id 或 --all-approved")

    ok = 0
    for pid in targets:
        if make_reel(pid, a.open and len(targets) == 1):
            ok += 1
    print("\n產出 %d/%d 支" % (ok, len(targets)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

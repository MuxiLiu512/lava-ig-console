#!/usr/bin/env python3
# _thumbs.py — 縮圖共用模組。
# 產出策略：長邊縮到 1080；優先用系統 cwebp 產 webp（repo 最輕），
# 無 cwebp 時退回 PIL 產 JPEG（q82）。回傳實際輸出的相對副檔名。
# 兩種格式前端都能顯示；沿用哪種由執行環境有無 cwebp 決定，不影響 posts.json 之外的邏輯。
import os, shutil, subprocess, tempfile

LONG_EDGE = 1080
JPEG_Q = 82
_HAS_CWEBP = shutil.which("cwebp") is not None

try:
    from PIL import Image
except Exception:
    Image = None


def _resized_tmp_png(src, long_edge):
    """用 PIL 把來源等比縮到長邊 long_edge，輸出暫存 PNG，回傳路徑。"""
    im = Image.open(src).convert("RGB")
    w, h = im.size
    scale = min(1.0, long_edge / max(w, h))
    if scale < 1.0:
        im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))))
    fd, p = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    im.save(p, "PNG")
    return p


def make_thumb(src, dst_noext, long_edge=LONG_EDGE):
    """把 src 縮圖存到 dst_noext + (.webp|.jpg)。回傳實際輸出路徑。
    dst_noext 不含副檔名，例如 assets/<id>/slide-1a。"""
    os.makedirs(os.path.dirname(dst_noext), exist_ok=True)
    if _HAS_CWEBP and Image is not None:
        tmp = _resized_tmp_png(src, long_edge)
        out = dst_noext + ".webp"
        try:
            subprocess.run(["cwebp", "-quiet", "-q", "80", tmp, "-o", out], check=True)
            return out
        finally:
            os.remove(tmp)
    if Image is not None:
        im = Image.open(src).convert("RGB")
        w, h = im.size
        scale = min(1.0, long_edge / max(w, h))
        if scale < 1.0:
            im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))))
        out = dst_noext + ".jpg"
        im.save(out, "JPEG", quality=JPEG_Q, optimize=True)
        return out
    # 最後手段：無 PIL 也無 cwebp，直接複製原檔（保留副檔名）
    ext = os.path.splitext(src)[1].lower() or ".jpg"
    out = dst_noext + ext
    shutil.copyfile(src, out)
    return out

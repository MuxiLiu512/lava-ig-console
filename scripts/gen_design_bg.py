#!/usr/bin/env python3
# gen_design_bg.py — 品牌設計底生成器（Tier 1 預設視覺，Weekend Club 式文字卡底）。
#
# 直接產 1950×2438 PNG（渲染引擎原生尺寸，fit_bg 成 no-op）。
# 四款模板：dusk 深漸層+橘光暈｜slash 雙色斜切｜grain 細紋理｜grid 暗色格點。
# 亮度預補償：引擎會再疊固定遮罩（cover 底部只保留 ~17% 亮度）→ 視覺重心一律放頂部
# 0-40%H、亮部以目標亮度×2 作畫、底部維持深色；全模板加噪點防 banding。
# 檔名 slide{N}-DESIGN-{tpl}-s{seed}.png（可被 slide-N regex 收錄；DESIGN 為 source_kind 錨點）。
#
# 用法：python3 gen_design_bg.py --draft <文案.json> --outdir <Drive底圖資料夾> [--per-slide 2] [--seed N]
import os, sys, json, argparse, zlib, random, math

from PIL import Image, ImageDraw, ImageFilter

W, H = 1950, 2438
ORANGE = (232, 66, 36)     # Lava Orange #E84224
ORANGE_DIM = (150, 43, 23) # 斜帶用（預補償後約呈 55% 亮度）
YELLOW = (250, 210, 40)    # 重點黃 #FAD228
DEEP = (11, 11, 12)        # 深底
EMBER = (26, 14, 11)       # 暗琥珀
TPLS = ["dusk", "slash", "grain", "grid"]


def _noise(im, strength=0.05):
    """細噪點疊加，防遮罩 alpha 相乘後 banding。"""
    n = Image.effect_noise((W // 2, H // 2), 24).resize((W, H)).convert("L")
    grain = Image.merge("RGB", (n, n, n))
    return Image.blend(im, grain, strength)


def _grad(c1, c2, tilt=0.25):
    """由上往下線性漸層（tilt 讓左右稍微傾斜）。"""
    base = Image.new("RGB", (2, 256))
    d = ImageDraw.Draw(base)
    for y in range(256):
        t = y / 255
        d.point([(0, y), (1, y)], fill=tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3)))
    return base.resize((W, H), Image.BICUBIC)


def _radial_glow(im, cx, cy, radius, color, peak_alpha):
    glow = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(glow)
    steps = 40
    for i in range(steps, 0, -1):
        r = radius * i / steps
        a = int(peak_alpha * (1 - i / steps) ** 1.5)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=a)
    glow = glow.filter(ImageFilter.GaussianBlur(60))
    layer = Image.new("RGB", (W, H), color)
    return Image.composite(layer, im, glow)


def make_bg(tpl, seed):
    rnd = random.Random(seed)
    if tpl == "dusk":
        im = _grad(EMBER, DEEP, rnd.uniform(-0.4, 0.4))
        cx = int(W * rnd.uniform(0.2, 0.8)); cy = int(H * rnd.uniform(0.08, 0.30))
        im = _radial_glow(im, cx, cy, W * rnd.uniform(0.55, 0.8), ORANGE, 170)  # 預補償：引擎遮罩會再壓暗
    elif tpl == "slash":
        im = Image.new("RGB", (W, H), DEEP)
        d = ImageDraw.Draw(im, "RGBA")
        ang = math.radians(rnd.uniform(18, 32))
        bw = int(H * rnd.uniform(0.12, 0.20))
        cyy = int(H * rnd.uniform(0.16, 0.34))
        dx = int(math.tan(ang) * H)
        d.polygon([(0, cyy), (W, cyy - dx), (W, cyy - dx + bw), (0, cyy + bw)], fill=ORANGE_DIM + (255,))
        off = int(rnd.uniform(40, 90))
        d.line([(0, cyy + bw + off), (W, cyy - dx + bw + off)], fill=YELLOW + (150,), width=6)
        im = im.filter(ImageFilter.GaussianBlur(1))
    elif tpl == "grain":
        base = (16, 16, 18)
        im = Image.new("RGB", (W, H), base)
        d = ImageDraw.Draw(im, "RGBA")
        gap = int(rnd.uniform(90, 140))
        for x in range(-H, W + H, gap):
            d.line([(x, 0), (x + H, H)], fill=(255, 255, 255, 10), width=2)
        cx = int(W * rnd.uniform(0.25, 0.75))
        im = _radial_glow(im, cx, int(H * 0.18), W * 0.6, (96, 82, 74), 120)
    else:  # grid — 必疊弱漸層保底（防 flat 誤殺的第二保險）
        im = _grad(EMBER, DEEP, 0.2)
        d = ImageDraw.Draw(im, "RGBA")
        gap = int(rnd.uniform(72, 112))
        dot_col = (255, 255, 255, 20) if rnd.random() < 0.5 else (232, 66, 36, 30)
        for y in range(gap // 2, H, gap):
            for x in range(gap // 2, W, gap):
                d.ellipse([x - 2, y - 2, x + 2, y + 2], fill=dot_col)
        gx = [0.2, 0.62, 0.2, 0.62][seed % 4]; gy = [0.12, 0.12, 0.28, 0.28][seed % 4]
        rw, rh = int(W * 0.30), int(H * 0.12)
        x0, y0 = int(W * gx), int(H * gy)
        d.rectangle([x0, y0, x0 + rw, y0 + rh], outline=(250, 210, 40, 150), width=4)
    return _noise(im)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft", required=True, help="文案 JSON（決定 slide 數與 CTA 排除）")
    ap.add_argument("--outdir", required=True, help="輸出資料夾（Drive 底圖資料夾）")
    ap.add_argument("--per-slide", type=int, default=2)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--post-id", default=None, help="seed 材料（預設用 draft 檔名）")
    a = ap.parse_args()
    with open(a.draft, encoding="utf-8") as f:
        d = json.load(f)
    base_key = a.post_id or os.path.basename(a.draft)
    os.makedirs(a.outdir, exist_ok=True)
    made = 0
    for s in d.get("slides", []):
        n = s.get("index")
        if "CTA" in str(s.get("role", "")).upper():
            continue
        # 每 slide 取 2 款不同模板（由 seed 決定起點，跨貼文不同臉、同貼文可重現）
        seed0 = a.seed if a.seed is not None else zlib.crc32(("%s|%s" % (base_key, n)).encode("utf-8"))
        start = seed0 % len(TPLS)
        for v in range(a.per_slide):
            tpl = TPLS[(start + v * 2 + (v > 1)) % len(TPLS)]
            seed = (seed0 + v * 7919) & 0xFFFF
            fn = "slide%d-DESIGN-%s-s%d.png" % (n, tpl, seed)
            fp = os.path.join(a.outdir, fn)
            if os.path.exists(fp):
                continue  # 冪等
            tmp = fp + ".part"   # 原子寫入：先寫暫存再 rename，被 timeout 砍掉不留截斷檔
            make_bg(tpl, seed).save(tmp, "PNG", optimize=True)
            os.replace(tmp, fp)
            made += 1
    print("✓ 設計底 %d 張 → %s" % (made, a.outdir))


if __name__ == "__main__":
    main()

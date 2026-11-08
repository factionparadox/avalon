#!/usr/bin/env python3
"""render-garden.py: Avalon's wallpaper, a garden drawn the way a 1999 PlayStation garden
simulation drew its gardens (Pixygarden is the model). Original scene and sprites; what it follows
is that look:

  - a flat pale-lavender sky, low blocky hills in the haze, a row of soft pastel lights
  - tall, narrow, sparse cedars in grey-green mist and a dark line of scrub at the meadow's end
  - a wide, smooth, dark green meadow plateau ending in a grassy lip over dark earth
  - pre-rendered-looking sprites with soft shading: spotted gourds held up on leafy plants,
    a red amaranth, a spiky green plant, tan cones, a bent reed, sprouts, bubbles with a
    sleeping pixie curled inside, two pixies on the wing
  - beacons: glossy black octahedra striped red, framed by four glowing cyan bars, spiked
  - soft dark shadows under everything; distance fog; 480x320, 15-bit colour with ordered
    dithering, scaled up 6x with hard pixels

    python3 build/render-garden.py        writes desktop/usr/share/avalon/garden-wallpaper.png

    python3 build/render-garden.py --pixies DIR --out FILE
        your own pixie sprites (PNGs with transparent backgrounds, in DIR) in place of Avalon's,
        written to FILE and nowhere else; put FILE at ~/.config/avalon/wallpaper and the Garden
        uses it in place of the stock wallpaper
"""
import math
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent.parent
OUT = HERE / 'desktop/usr/share/avalon/garden-wallpaper.png'
RW, RH = 480, 320          # the render
SCALE = 6                  # 2880x1920
rng = random.Random(1999)

MIST = np.array([176, 172, 190], np.float32)
FOG_NEAR, FOG_FAR = 8.0, 70.0


# ---------------------------------------------------------------- camera
CAM = np.array([0.0, 1.6, 0.0])
PITCH = math.radians(-6.5)         # nearly level, as the game's garden camera was
FOV = math.radians(56)
F = (RW / 2) / math.tan(FOV / 2)
CX, CY = RW / 2, RH / 2
_c, _s = math.cos(PITCH), math.sin(PITCH)
R = np.array([[1, 0, 0], [0, _c, _s], [0, -_s, _c]], np.float64)
RT = R.T


def project(p):
    cx, cy, cz = RT @ (np.asarray(p, np.float64) - CAM)
    if cz <= 0.05:
        return None
    return (CX + F * cx / cz, CY - F * cy / cz, cz)


def fog_amount(depth):
    return float(np.clip((depth - FOG_NEAR) / (FOG_FAR - FOG_NEAR), 0, 1)) ** 0.8


# --------------------------------------------------------------- textures
def tex(size, base, spread, seed, grain=1.0, levels=5):
    g = np.random.default_rng(seed)
    n = g.random((size, size)).astype(np.float32)
    big = np.tile(n, (3, 3))       # blurred with wrap-around, so tiles meet without a seam
    im = Image.fromarray((big * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(grain))
    n = np.asarray(im).astype(np.float32)[size:2 * size, size:2 * size] / 255
    n = (n - n.min()) / max(1e-6, n.max() - n.min())
    q = np.floor(n * levels) / (levels - 1)
    t = np.zeros((size, size, 3), np.float32)
    for i in range(3):
        t[:, :, i] = base[i] * (1 - spread / 2 + spread * q)
    return np.clip(t, 0, 255)


GRASS = tex(64, (58, 98, 48), 0.32, 1, grain=1.4, levels=6)       # smooth, dark, low contrast
GRASS_BIG = tex(64, (58, 98, 48), 0.22, 5, grain=3.0, levels=4)   # broad mottling
SOIL = tex(64, (46, 40, 44), 0.45, 3, grain=1.6, levels=5)


# ------------------------------------------------------- ground and sky (per pixel)
def ground_and_sky():
    ys, xs = np.mgrid[0:RH, 0:RW].astype(np.float32)
    dx = (xs - CX) / F
    dy = -(ys - CY) / F
    dz = np.ones_like(dx)
    wx = R[0, 0] * dx + R[0, 1] * dy + R[0, 2] * dz
    wy = R[1, 0] * dx + R[1, 1] * dy + R[1, 2] * dz
    wz = R[2, 0] * dx + R[2, 1] * dy + R[2, 2] * dz

    # sky: an almost flat pale lavender, a touch lighter low down
    elev = np.clip(wy / np.sqrt(wx * wx + wy * wy + wz * wz), -1, 1)
    t = np.clip(elev / 0.5, 0, 1)[:, :, None]
    img = np.array([190, 186, 202], np.float32) * (1 - t) + np.array([176, 172, 194], np.float32) * t
    depth = np.full((RH, RW), 1e9, np.float32)

    # the plateau: y = 0 from the edge at z = EDGE out to the far scrub
    EDGE = 4.4
    with np.errstate(divide='ignore', invalid='ignore'):
        tg = np.where(wy < -1e-4, -CAM[1] / wy, np.inf)
        gx = np.nan_to_num(CAM[0] + wx * tg, nan=0, posinf=0, neginf=0)
        gz = np.nan_to_num(CAM[2] + wz * tg, nan=0, posinf=0, neginf=0)
    # the edge isn't ruler-straight: it wanders a little
    on_ground = np.isfinite(tg) & (gz >= EDGE)
    u = np.floor(gx * 24).astype(int) % 64
    v = np.floor(gz * 24).astype(int) % 64
    u2 = np.floor(gx * 5).astype(int) % 64
    v2 = np.floor(gz * 5).astype(int) % 64
    g = GRASS[v, u] * 0.55 + GRASS_BIG[v2, u2] * 0.45
    # the meadow lightens and greys a little with distance (before the fog proper)
    g = g * np.clip(1.0 + 0.004 * gz, 1.0, 1.15)[:, :, None]
    img = np.where(on_ground[:, :, None], g, img)
    depth = np.where(on_ground, tg, depth)

    # the face under the edge: dark earth, with the grass hanging over its top
    with np.errstate(divide='ignore', invalid='ignore'):
        tw = np.where(wz > 1e-4, (EDGE - CAM[2]) / wz, np.inf)
        wyy = np.nan_to_num(CAM[1] + wy * tw, nan=99, posinf=99, neginf=99)
        wxx = np.nan_to_num(CAM[0] + wx * tw, nan=0, posinf=0, neginf=0)
    face = ~on_ground & (wy < 0)
    su = np.floor(wxx * 20).astype(int) % 64
    sv = np.floor(-np.minimum(wyy, 0) * 20).astype(int) % 64
    soil = SOIL[sv, su] * np.clip(1 + wyy * 0.12, 0.55, 1)[:, :, None]
    # the lip: blades of grass hanging over, longer in places
    blade = (np.floor(wxx * 26) % 3 == 0) | (np.floor(wxx * 17 + 0.5) % 4 == 0)
    lip_len = 0.05 + 0.04 * np.abs(np.sin(wxx * 2.1)) + np.where(blade, 0.05, 0.0)
    lip = (wyy > -lip_len) & (wyy < 0.02)
    lipcol = GRASS[sv % 64, su % 64] * np.clip(0.85 + wyy * 4.0, 0.4, 0.85)[:, :, None]
    soil = np.where(lip[:, :, None], lipcol, soil)
    img = np.where(face[:, :, None], soil, img)
    depth = np.where(face, np.where(np.isfinite(tw), tw, 1.0), depth)

    a = np.clip((depth - FOG_NEAR) / (FOG_FAR - FOG_NEAR), 0, 1) ** 0.8
    a = np.where(depth > 1e8, 0, a)[:, :, None]
    img = img * (1 - a) + MIST * a
    return img, depth


# ------------------------------------------------------------- drawing
def draw_billboard(img, depthbuf, sprite, world_base, height_m, soft=False):
    """a sprite standing at world_base, height_m tall, depth-tested per pixel, fogged.
    soft: keep its alpha (bubbles, wings, glows) instead of cutting it hard"""
    p = project(world_base)
    if not p:
        return
    sx, sy, z = p
    hp = int(round(F * height_m / z))
    if hp < 2:
        return
    wp = max(1, int(round(hp * sprite.width / sprite.height)))
    spr = sprite.resize((wp, hp), Image.BOX if soft else Image.NEAREST)
    a = np.asarray(spr).astype(np.float32)
    fa = fog_amount(z)
    col = a[:, :, :3] * (1 - fa) + MIST * fa
    x0, y0 = int(round(sx - wp / 2)), int(round(sy - hp))
    xa, ya = max(0, x0), max(0, y0)
    xb, yb = min(RW, x0 + wp), min(RH, y0 + hp)
    if xa >= xb or ya >= yb:
        return
    al = a[ya - y0:yb - y0, xa - x0:xb - x0, 3] / 255
    if not soft:
        al = (al > 0.5).astype(np.float32)
    nearer = depthbuf[ya:yb, xa:xb] > z
    al = al * nearer
    sub = img[ya:yb, xa:xb]
    sub[:] = sub * (1 - al[:, :, None]) + col[ya - y0:yb - y0, xa - x0:xb - x0] * al[:, :, None]
    depthbuf[ya:yb, xa:xb] = np.where(al > 0.5, z, depthbuf[ya:yb, xa:xb])


def draw_mesh(img, depthbuf, verts, faces, colours, light=(-0.5, 0.75, -0.45)):
    """flat-shaded polygons, painter-sorted, fogged; colours: one per face, or one for all"""
    L = np.array(light) / np.linalg.norm(light)
    pv = [project(v) for v in verts]
    order = []
    for i, f in enumerate(faces):
        if any(pv[k] is None for k in f):
            continue
        a, b, c = (np.array(verts[k]) for k in f[:3])
        n = np.cross(b - a, c - a)
        nn = np.linalg.norm(n)
        if nn == 0:
            continue
        n /= nn
        centre = np.mean([verts[k] for k in f], axis=0)
        if np.dot(n, CAM - centre) <= 0:
            continue
        z = np.mean([pv[k][2] for k in f])
        lum = 0.35 + 0.65 * max(0, float(np.dot(n, L)))
        spec = max(0, float(np.dot(n, L))) ** 12 * 0.6           # a glint: they're glossy
        col = colours[i] if isinstance(colours, list) else colours
        order.append((z, f, lum, spec, col))
    order.sort(key=lambda o: -o[0])
    layer = Image.new('RGBA', (RW, RH), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    zmin = 1e9
    for z, f, lum, spec, col in order:
        c = tuple(min(255, int(ch * lum + 255 * spec)) for ch in col)
        fa = fog_amount(z)
        c = tuple(int(c[k] * (1 - fa) + MIST[k] * fa) for k in range(3))
        d.polygon([(round(pv[k][0]), round(pv[k][1])) for k in f], fill=c + (255,))
        zmin = min(zmin, z)
    arr = np.asarray(layer).astype(np.float32)
    m = (arr[:, :, 3] > 0) & (depthbuf > zmin)
    img[m] = arr[:, :, :3][m]
    depthbuf[m] = np.minimum(depthbuf[m], zmin)


def ground_shadow(img, depthbuf, x, z, rx, rz, strength=0.45):
    pts = [project((x + rx * math.cos(t), 0.0, z + rz * math.sin(t))) for t in np.linspace(0, 2 * math.pi, 24)]
    if any(p is None for p in pts):
        return
    layer = Image.new('L', (RW, RH), 0)
    ImageDraw.Draw(layer).polygon([(p[0], p[1]) for p in pts], fill=255)
    m = np.asarray(layer.filter(ImageFilter.GaussianBlur(1.6))).astype(np.float32) / 255
    m *= (depthbuf > z - rz * 2)
    img *= (1 - strength * m)[:, :, None]


# ------------------------------------------------------------- sprites
def shaded_blob(w, h, base, light=(-0.45, -0.55), rim=0.55, spots=None, seed=0):
    """an ellipsoid with soft, pre-rendered-looking shading; RGBA"""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    nx = (xx - w / 2 + 0.5) / (w / 2)
    ny = (yy - h / 2 + 0.5) / (h / 2)
    r2 = nx * nx + ny * ny
    inside = r2 <= 1
    nz = np.sqrt(np.clip(1 - r2, 0, 1))
    lx, ly = light
    lz = math.sqrt(max(0, 1 - lx * lx - ly * ly))
    lam = np.clip(nx * lx + ny * ly + nz * lz, 0, 1)
    shade = rim + (1 - rim) * lam + 0.35 * lam ** 18
    col = np.clip(np.array(base, np.float32)[None, None, :] * shade[:, :, None], 0, 255)
    if spots:
        g = random.Random(seed)
        for _ in range(spots):
            sx, sy = g.uniform(0.15, 0.85) * w, g.uniform(0.15, 0.85) * h
            rr = g.uniform(0.6, 1.4)
            m = (xx - sx) ** 2 + (yy - sy) ** 2 < rr * rr
            col[m] *= 0.55
    out = np.dstack([col, inside * 255.0]).astype(np.uint8)
    return Image.fromarray(out, 'RGBA')


def leaf_poly(d, base, tip, width, colour, vein):
    bx, by = base; tx, ty = tip
    ang = math.atan2(ty - by, tx - bx)
    nx, ny = -math.sin(ang) * width, math.cos(ang) * width
    mx, my = bx + (tx - bx) * 0.45, by + (ty - by) * 0.45
    d.polygon([(bx, by), (mx + nx, my + ny), (tx, ty), (mx - nx, my - ny)], fill=colour)
    d.line([(bx, by), (tx, ty)], fill=vein)


def gourd_plant(seed):
    """a spotted orange gourd held up on a rosette of broad, ribbed leaves"""
    r = random.Random(seed)
    W, H = 96, 112
    s = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(s)
    for k in range(9):                                  # the rosette
        a = math.radians(-170 + k * 20 + r.uniform(-6, 6))
        L = r.uniform(30, 44)
        tip = (48 + math.cos(a) * L, 84 + math.sin(a) * L * 0.55 + 14)
        shade = r.uniform(0.75, 1.05)
        leaf_poly(d, (48, 82), tip, r.uniform(7, 10), (int(76 * shade), int(128 * shade), int(70 * shade), 255),
                  (int(150 * shade), int(186 * shade), int(132 * shade), 255))
    d.rectangle([45, 46, 51, 84], fill=(78, 108, 56, 255))   # the stalk up to the gourd
    body = shaded_blob(70, 54, (216, 150, 54), spots=46, seed=seed)
    s.alpha_composite(body, (13, 4))
    bd = ImageDraw.Draw(s)                              # ribs
    for x0 in (30, 40, 48, 56, 66):
        bd.arc([x0 - 14, 6, x0 + 14, 56], 250, 290, fill=(150, 92, 34, 255))
    for k in range(4):                                  # leaves in front
        a = math.radians(r.choice([20, 55, 125, 160]) + r.uniform(-8, 8))
        L = r.uniform(24, 34)
        tip = (48 + math.cos(a) * L, 92 + math.sin(a) * L * 0.4)
        leaf_poly(bd, (48, 86), tip, r.uniform(7, 9), (98, 150, 84, 255), (168, 204, 150, 255))
    return s


def amaranth(seed):
    """a dense, dark red plant, its plumes drooping"""
    r = random.Random(seed)
    W, H = 70, 100
    s = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(s)
    for _ in range(420):
        y = r.uniform(4, 96)
        spread = 6 + 26 * (y / 100) ** 0.7
        x = r.gauss(W / 2, spread / 2)
        c = r.choice([(150, 40, 30), (176, 54, 36), (120, 32, 28), (196, 78, 46), (98, 30, 26)])
        sh = 0.75 + 0.35 * (1 - abs(x - W / 2) / 35)
        d.ellipse([x - 2, y - 1.5, x + 2, y + 1.5], fill=tuple(min(255, int(ch * sh)) for ch in c) + (255,))
    return s


def spiky_plant(seed):
    """long sword-like green leaves from a tuft"""
    r = random.Random(seed)
    W, H = 70, 100
    s = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(s)
    for _ in range(26):
        a = math.radians(r.uniform(-160, -20))
        L = r.uniform(40, 95)
        tip = (35 + math.cos(a) * L * 0.6, 98 + math.sin(a) * L)
        sh = r.uniform(0.7, 1.1)
        leaf_poly(d, (35 + r.uniform(-4, 4), 98), tip, r.uniform(2, 3.2), (int(70 * sh), int(124 * sh), int(56 * sh), 255),
                  (int(120 * sh), int(170 * sh), int(96 * sh), 255))
    return s


def cones(seed):
    """three tan cones, rounded at the tip, speckled"""
    r = random.Random(seed)
    W, H = 80, 64
    s = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    for cx, h, w in ((22, 60, 20), (46, 40, 15), (64, 34, 13)):
        yy, xx = np.mgrid[0:h, 0:2 * w].astype(np.float32)
        half = w * (yy / h) ** 0.75                       # rounded shoulders
        inside = np.abs(xx - w) <= half
        nx = (xx - w) / np.maximum(half, 1)
        lam = np.clip(0.55 - 0.5 * nx, 0, 1)
        col = np.array([196, 160, 112], np.float32)[None, None, :] * (0.55 + 0.6 * lam)[:, :, None]
        g = np.random.default_rng(seed * 7 + cx)
        col *= (1 - 0.35 * (g.random((h, 2 * w)) > 0.9))[:, :, None]
        arr = np.dstack([np.clip(col, 0, 255), inside * 255.0]).astype(np.uint8)
        s.alpha_composite(Image.fromarray(arr, 'RGBA'), (cx - w, H - h))
    return s


def reed(seed):
    s = Image.new('RGBA', (40, 120), (0, 0, 0, 0))
    d = ImageDraw.Draw(s)
    d.line([(14, 120), (16, 70), (22, 30), (34, 6)], fill=(110, 150, 84, 255), width=2)
    d.line([(16, 120), (18, 80), (24, 50)], fill=(80, 118, 62, 255), width=1)
    return s


def sprout(seed):
    r = random.Random(seed)
    s = Image.new('RGBA', (36, 36), (0, 0, 0, 0))
    d = ImageDraw.Draw(s)
    d.line([(18, 36), (18, 14)], fill=(96, 132, 70, 255), width=2)
    for a in (-150, -30, -110, -70):
        a = math.radians(a + r.uniform(-10, 10))
        leaf_poly(d, (18, 18), (18 + math.cos(a) * 15, 18 + math.sin(a) * 10), 4, (104, 156, 84, 255), (150, 196, 128, 255))
    return s


def cedar(h_px, seed):
    """a tall, narrow cedar: a straight trunk, foliage in sparse ragged layers with sky between"""
    r = random.Random(seed)
    w_px = int(h_px * 0.30)
    s = Image.new('RGBA', (w_px, h_px), (0, 0, 0, 0))
    d = ImageDraw.Draw(s)
    cx = w_px / 2
    d.line([(cx, h_px), (cx, h_px * 0.04)], fill=(70, 66, 62, 255), width=max(1, h_px // 60))
    y = h_px * 0.03
    while y < h_px * 0.72:
        f = y / h_px
        hw = w_px * (0.12 + 0.40 * min(1, f / 0.55)) * r.uniform(0.6, 1.05)
        side = r.choice([-1, 1, 0])
        for _ in range(r.randint(10, 18)):               # a layer: a flat clump of needles
            px = cx + side * hw * 0.2 + r.uniform(-hw, hw)
            py = y + r.uniform(-h_px * 0.012, h_px * 0.03)
            rw = r.uniform(2, 4.5)
            g = r.choice([(64, 90, 66), (76, 102, 76), (56, 80, 60), (88, 112, 86)])
            d.ellipse([px - rw, py - rw * 0.45, px + rw, py + rw * 0.45], fill=g + (255,))
        y += h_px * r.uniform(0.035, 0.07)
    return s


def scrub(seed):
    """the dark line of bushes where the meadow ends"""
    r = random.Random(seed)
    W, H = 480, 40
    s = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(s)
    for _ in range(700):
        x = r.uniform(0, W)
        top = 12 + 8 * math.sin(x / 23) + 5 * math.sin(x / 7.7)
        y = r.uniform(top, H)
        rr = r.uniform(2, 5)
        g = r.choice([(44, 66, 48), (52, 76, 54), (38, 58, 42), (60, 84, 60)])
        d.ellipse([x - rr, y - rr * 0.7, x + rr, y + rr * 0.7], fill=g + (255,))
    return s


def hills():
    s = Image.new('RGBA', (480, 60), (0, 0, 0, 0))
    d = ImageDraw.Draw(s)
    pts = [(0, 60)]
    for x in range(0, 484, 12):                          # blocky, as the haze gives them
        pts += [(x, 22 + 12 * math.sin(x / 61) + 6 * math.sin(x / 19 + 1)), (x + 12, 22 + 12 * math.sin(x / 61) + 6 * math.sin(x / 19 + 1))]
    pts += [(480, 60)]
    d.polygon(pts, fill=(120, 116, 136, 255))
    return s


def bubble(seed):
    """a clear bubble with a pale pixie asleep inside, curled up"""
    S = 64
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
    nx, ny = (xx - S / 2 + 0.5) / (S / 2), (yy - S / 2 + 0.5) / (S / 2)
    r2 = nx * nx + ny * ny
    inside = r2 <= 1
    rim = np.clip((r2 - 0.55) / 0.45, 0, 1) ** 2
    col = np.array([196, 214, 240], np.float32)[None, None, :] * np.ones((S, S, 1), np.float32)
    alpha = (0.18 + 0.7 * rim) * inside
    s = Image.fromarray(np.dstack([col, alpha * 255]).astype(np.uint8), 'RGBA')
    d = ImageDraw.Draw(s)
    # the sleeper: a small pixie curled up, knees drawn in, hair falling over them, wings folded
    d.ellipse([18, 26, 40, 40], fill=(214, 226, 236, 120))           # folded wings
    d.ellipse([24, 30, 44, 48], fill=(238, 228, 236, 220))           # back and legs, curled
    d.ellipse([34, 38, 46, 50], fill=(246, 230, 226, 230))           # knees
    d.ellipse([22, 20, 34, 32], fill=(246, 228, 220, 235))           # head, bowed
    d.pieslice([19, 17, 37, 35], 150, 360, fill=(222, 214, 236, 240))  # pale hair
    d.line([(36, 26), (40, 40)], fill=(222, 214, 236, 220), width=2)
    d.ellipse([14, 10, 26, 20], fill=(255, 255, 255, 230))           # the bubble's glint
    return s


ELEMENTS = {   # Avalon's four elements, as the HUD has them: hair, dress, wing tint
    'wind':  ((236, 226, 150), (226, 214, 120), (210, 236, 190)),
    'earth': ((150, 104, 70), (124, 150, 82), (214, 200, 150)),
    'fire':  ((222, 92, 70), (204, 70, 64), (246, 190, 150)),
    'water': ((96, 140, 214), (90, 120, 200), (176, 214, 246)),
}


WING_SHAPES = {   # (centre x, centre y, half-length, half-width, angle) for each wing
    'butterfly': ((52, 62, 44, 24, 30), (108, 62, 44, 24, -30), (58, 98, 30, 16, -25), (102, 98, 30, 16, 25)),
    'dragonfly': ((44, 66, 56, 9, 12), (116, 66, 56, 9, -12), (46, 80, 50, 8, -6), (114, 80, 50, 8, 6)),
    'moth':      ((50, 72, 46, 30, 18), (110, 72, 46, 30, -18)),
    'petal':     ((56, 54, 36, 14, 55), (104, 54, 36, 14, -55), (52, 86, 34, 13, 20), (108, 86, 34, 13, -20)),
}


def _wing(rw, rh, ang, tint, mirrored, spots=False):
    yy, xx = np.mgrid[0:140, 0:140].astype(np.float32)
    t = math.radians(ang)
    X = ((xx - 70) * math.cos(t) + (yy - 70) * math.sin(t)) / rw
    Y = (-(xx - 70) * math.sin(t) + (yy - 70) * math.cos(t)) / rh
    r2 = X * X + Y * Y
    inside = r2 <= 1
    al = np.where(inside, 0.45 + 0.5 * r2 ** 3, 0)
    col = np.ones((140, 140, 3), np.float32) * np.array(tint, np.float32) * (0.85 + 0.3 * (1 - r2[:, :, None]).clip(0, 1))
    if spots:                                              # eye-spots, as moths have
        m = ((X - 0.35) ** 2 + Y ** 2 * 2) < 0.06
        col[m] = col[m] * 0.6
        al = np.where(m & inside, 0.9, al)
    img = Image.fromarray(np.dstack([col.clip(0, 255), al * 255]).astype(np.uint8), 'RGBA')
    d = ImageDraw.Draw(img)
    for k in (-0.35, 0.0, 0.35):                           # veins fanning from the root
        ex = 70 + math.cos(t + k) * rw * 0.85 * (-1 if mirrored else 1)
        ey = 70 + math.sin(t + k) * rw * 0.85 * (-1 if mirrored else 1)
        d.line([(70, 70), (ex, ey)], fill=tuple(min(255, c + 40) for c in tint) + (140,))
    return img


def pixie(element, wings='butterfly', hair_style='long', pose='fly', flip=False):
    """one of Avalon's pixies, drawn large and shaded, then shrunk like a pre-rendered sprite.
    wings: butterfly, dragonfly, moth, petal; hair: long, bob, twintails; pose: fly, sit, kneel"""
    hair, dress, wing = ELEMENTS[element]
    W, H = 160, 190
    s = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    for (cx, cy, rw, rh, ang) in WING_SHAPES[wings]:
        if pose != 'fly':                                  # resting: wings raised and closer in
            cy -= 8; ang = ang * 1.6
        s.alpha_composite(_wing(rw, rh, ang, wing, cx < 80, spots=(wings == 'moth')), (int(cx - 70), int(cy - 70)))
    d = ImageDraw.Draw(s)
    skin, skin_sh = (246, 224, 210), (220, 190, 178)
    dark = tuple(int(c * 0.76) for c in dress)
    if pose == 'fly':                                      # legs trailing, arms out, gliding
        d.line([(76, 122), (68, 160), (62, 176)], fill=skin_sh, width=5)
        d.line([(84, 122), (88, 158), (96, 172)], fill=skin, width=5)
        d.polygon([(72, 74), (88, 74), (102, 130), (58, 130)], fill=dress)
        d.polygon([(82, 74), (88, 74), (102, 130), (86, 130)], fill=dark)
        d.line([(73, 80), (56, 96), (50, 106)], fill=skin, width=4)
        d.line([(87, 80), (104, 92), (112, 100)], fill=skin_sh, width=4)
    elif pose == 'sit':                                    # sitting, knees up, hands in her lap
        d.polygon([(72, 74), (88, 74), (98, 128), (60, 128)], fill=dress)
        d.polygon([(82, 74), (88, 74), (98, 128), (84, 128)], fill=dark)
        d.line([(66, 126), (60, 150), (70, 176)], fill=skin_sh, width=5)
        d.line([(92, 126), (100, 150), (92, 176)], fill=skin, width=5)
        d.line([(73, 82), (68, 104), (78, 116)], fill=skin, width=4)
        d.line([(87, 82), (92, 104), (82, 116)], fill=skin_sh, width=4)
    else:                                                  # kneeling, reaching down to a plant
        d.polygon([(70, 80), (88, 76), (104, 140), (60, 140)], fill=dress)
        d.polygon([(82, 77), (88, 76), (104, 140), (88, 140)], fill=dark)
        d.line([(66, 140), (84, 176), (110, 178)], fill=skin_sh, width=5)
        d.line([(88, 84), (106, 120), (118, 150)], fill=skin, width=4)
        d.line([(74, 86), (92, 124), (110, 152)], fill=skin_sh, width=4)
    hy = 0 if pose != 'kneel' else 8                       # head drops a little when kneeling
    if hair_style == 'long':
        d.polygon([(66, 40 + hy), (96, 40 + hy), (104, 86 + hy), (92, 70 + hy), (86, 92 + hy), (72, 70 + hy), (58, 84 + hy)], fill=hair)
    elif hair_style == 'twintails':
        d.ellipse([52, 48 + hy, 66, 92 + hy], fill=hair)
        d.ellipse([94, 48 + hy, 108, 92 + hy], fill=hair)
    else:                                                  # a bob
        d.ellipse([62, 34 + hy, 98, 70 + hy], fill=hair)
    d.ellipse([68, 38 + hy, 92, 64 + hy], fill=skin)
    d.ellipse([84, 44 + hy, 92, 62 + hy], fill=skin_sh)
    d.chord([64, 30 + hy, 96, 56 + hy], 180, 360, fill=hair)
    if pose == 'kneel':                                    # eyes down, on her work
        d.line([(72, 54 + hy), (75, 54 + hy)], fill=(60, 50, 70), width=2)
        d.line([(80, 54 + hy), (83, 54 + hy)], fill=(60, 50, 70), width=2)
    else:
        d.ellipse([72, 50 + hy, 75, 53 + hy], fill=(60, 50, 70))
        d.ellipse([80, 50 + hy, 83, 53 + hy], fill=(60, 50, 70))
    halo = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(halo).ellipse([30, 30, 130, 170], fill=wing + (60,))
    halo = halo.filter(ImageFilter.GaussianBlur(14))
    halo.alpha_composite(s)
    return halo.transpose(Image.FLIP_LEFT_RIGHT) if flip else halo


def youngling(element):
    """a newly hatched pixie, the stage between the bubble and the grown pixie: a small round
    body in a glow of her element, a big head, stubby wings still unfolding"""
    hair, dress, wing = ELEMENTS[element]
    W = H = 64
    s = glow(wing, 64)
    d = ImageDraw.Draw(s)
    for (x0, y0, x1, y1) in ((12, 18, 30, 32), (34, 18, 52, 32)):   # stubby wings
        d.ellipse([x0, y0, x1, y1], fill=wing + (170,), outline=tuple(min(255, c + 40) for c in wing) + (220,))
    d.ellipse([24, 30, 40, 48], fill=dress + (255,))                # round little body
    d.ellipse([22, 14, 42, 34], fill=(246, 228, 220, 255))          # big head
    d.chord([20, 10, 44, 30], 180, 360, fill=hair + (255,))         # hair
    d.ellipse([27, 22, 30, 25], fill=(60, 50, 70, 255))
    d.ellipse([34, 22, 37, 25], fill=(60, 50, 70, 255))
    return s


def glow(colour, size=24):
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    r = np.sqrt((xx - size / 2) ** 2 + (yy - size / 2) ** 2) / (size / 2)
    a = np.clip(1 - r, 0, 1) ** 1.6
    col = np.ones((size, size, 3), np.float32) * np.array(colour, np.float32)
    col = col * (1 - 0.5 * a[:, :, None]) + 255 * 0.5 * a[:, :, None]
    return Image.fromarray(np.dstack([col, a * 230]).astype(np.uint8), 'RGBA')


# ------------------------------------------------------------- the beacon
def beacon(img, depth, c, r):
    """a glossy black octahedron, striped red with a red jewel, inside a frame of four glowing
    cyan bars, a spike with a bead above and below"""
    x, y, z = c
    h = r * 1.35
    v = [(x, y + h, z), (x + r, y, z), (x, y, z - r), (x - r, y, z), (x, y, z + r), (x, y - h, z)]
    faces = [(0, 1, 2), (0, 2, 3), (0, 3, 4), (0, 4, 1), (5, 2, 1), (5, 3, 2), (5, 4, 3), (5, 1, 4)]
    draw_mesh(img, depth, v, faces, (34, 32, 40))
    p = project(c)
    if not p:
        return
    sx, sy, sz = p
    w = F * r / sz
    hh = F * h / sz
    layer = Image.new('RGBA', (RW, RH), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    # the red stripes across the upper and lower halves, and the jewel
    for f in (-0.45, 0.45):
        yy = sy + f * hh
        half = w * (1 - abs(f)) * 0.92
        d.line([(sx - half, yy), (sx + half, yy)], fill=(200, 30, 40, 255), width=max(1, int(w * 0.12)))
    j = w * 0.22
    d.polygon([(sx, sy - j), (sx + j, sy), (sx, sy + j), (sx - j, sy)], fill=(232, 40, 52, 255))
    # spikes and beads
    for sgn in (-1, 1):
        y0, y1 = sy + sgn * hh, sy + sgn * hh * 1.45
        d.polygon([(sx - w * 0.12, y0), (sx + w * 0.12, y0), (sx, y1)], fill=(24, 22, 28, 255))
        b = w * 0.13
        d.ellipse([sx - b, y1 - b, sx + b, y1 + b], fill=(24, 22, 28, 255))
    # the frame: four cyan bars parallel to the octahedron's edges, held a little off it
    gap = 1.28
    corners = [(sx, sy - hh * gap), (sx + w * gap, sy), (sx, sy + hh * gap), (sx - w * gap, sy)]
    bars = Image.new('RGBA', (RW, RH), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bars)
    for k in range(4):
        (ax, ay), (bx, by) = corners[k], corners[(k + 1) % 4]
        t0, t1 = 0.14, 0.86                               # broken at the corners
        p0 = (ax + (bx - ax) * t0, ay + (by - ay) * t0)
        p1 = (ax + (bx - ax) * t1, ay + (by - ay) * t1)
        bd.line([p0, p1], fill=(110, 230, 250, 255), width=max(2, int(w * 0.16)))
    visible = (depth >= sz - r * 1.5)[:, :, None]          # not over anything nearer
    halo = bars.filter(ImageFilter.GaussianBlur(2.2))
    for im_ in (halo, bars):
        arr = np.asarray(im_).astype(np.float32)
        al = arr[:, :, 3:4] / 255 * visible
        img[:] = img * (1 - al) + arr[:, :, :3] * al
    arr = np.asarray(layer).astype(np.float32)
    m = (arr[:, :, 3] > 0) & visible[:, :, 0]
    img[m] = arr[:, :, :3][m]


# ------------------------------------------------------------- the scene
def render(own_pixies=None):
    img, depth = ground_and_sky()
    own = list(own_pixies or [])

    def pixie_sprite(i, *args):
        if own:
            return own[i % len(own)]
        return pixie(*args)

    # far off: the hills in the haze, then the scrub at the meadow's end
    draw_billboard(img, depth, hills(), (-30, 0, 120), 14)
    draw_billboard(img, depth, scrub(1), (0, 0, 46), 3.4)

    # the cedars: tall and sparse, thickest to the right and at the back, a few to the left
    trees = []
    for _ in range(22):                                   # the far stand, right of centre
        trees.append((rng.uniform(38, 54), rng.uniform(0, 34), rng.uniform(17, 25)))
    for _ in range(5):                                    # a few ghosts far to the left
        trees.append((rng.uniform(52, 60), rng.uniform(-34, -18), rng.uniform(14, 18)))
    for x, z, hgt in ((9, 24, 20), (13, 20, 22), (17, 27, 24), (7.5, 30, 21), (21, 23, 25), (5.5, 36, 22)):
        trees.append((z, x, hgt))                         # nearer, darker cedars on the right
    trees.sort(key=lambda t: -t[0])
    for z, x, hgt in trees:
        draw_billboard(img, depth, cedar(220, int(x * 13 + z)), (x, 0, z), hgt)

    # the row of pastel lights hanging in the sky
    for k, c in enumerate([(150, 220, 240), (180, 170, 240), (230, 160, 220), (210, 190, 240), (240, 236, 250)]):
        draw_billboard(img, depth, glow(c), (-6.4 + k * 0.85, 3.3 + 0.08 * k, 20), 0.75, soft=True)

    # the garden's plants, furthest first, each with its shadow
    plants = [
        (amaranth(1), -3.9, 9.6, 1.7), (spiky_plant(2), -3.3, 10.6, 1.9),
        (gourd_plant(3), 0.4, 10.5, 1.5), (gourd_plant(4), 3.3, 8.6, 1.8),
        (cones(5), -2.3, 6.8, 0.7), (reed(6), 1.4, 7.4, 1.5),
        (sprout(7), -1.3, 9.4, 0.5), (sprout(8), 2.4, 12.0, 0.45), (sprout(9), -0.5, 7.0, 0.4),
        (spiky_plant(10), 6.0, 15.5, 1.6), (amaranth(11), 7.0, 17.0, 1.5),
    ]
    for spr, x, z, hgt in plants:
        ground_shadow(img, depth, x, z, hgt * 0.32, hgt * 0.16, 0.42)
    for spr, x, z, hgt in sorted(plants, key=lambda p: -p[2]):
        draw_billboard(img, depth, spr, (x, 0, z), hgt)

    # bubbles, pixies asleep inside, resting on the grass
    for x, z, s in ((-0.9, 7.6, 0.62), (-0.15, 7.1, 0.42)):
        ground_shadow(img, depth, x, z, s * 0.4, s * 0.2, 0.3)
        draw_billboard(img, depth, bubble(1), (x, 0.02, z), s, soft=True)

    # younglings, just out of their bubbles, hovering low by the bubbles and the sprouts
    for x, y, z, el, size in ((-0.45, 0.55, 7.0, 'water', 0.34), (-1.6, 0.4, 9.0, 'wind', 0.3),
                              (0.9, 0.7, 10.0, 'fire', 0.3)):
        ground_shadow(img, depth, x, z, size * 0.25, size * 0.12, 0.2)
        draw_billboard(img, depth, youngling(el), (x, y, z), size, soft=True)

    # beacons floating over the meadow, their shadows below
    for c, r in (((-1.5, 1.5, 9.0), 0.34), ((6.3, 1.9, 12.0), 0.34)):
        ground_shadow(img, depth, c[0], c[2], r * 1.2, r * 0.7, 0.32)
        beacon(img, depth, c, r)

    # the pixies about the garden: different kinds, different elements, flying and resting
    flyers = ((-2.9, 0.95, 8.4, 'fire', 'butterfly', 'long', False, 1.25),
              (1.7, 1.30, 10.5, 'water', 'dragonfly', 'bob', True, 1.15),
              (-0.3, 1.95, 13.0, 'wind', 'petal', 'twintails', False, 1.0),
              (-5.2, 2.3, 16.0, 'earth', 'moth', 'bob', True, 1.0),
              (3.2, 2.6, 17.0, 'fire', 'dragonfly', 'twintails', False, 0.95))
    for i, (x, y, z, el, w, hs, flip, size) in enumerate(flyers):
        ground_shadow(img, depth, x, z, size * 0.25, size * 0.12, 0.22)
        draw_billboard(img, depth, pixie_sprite(i, el, w, hs, 'fly', flip), (x, y, z), size, soft=True)
    # one sitting on top of the near gourd, one kneeling to tend a sprout
    draw_billboard(img, depth, pixie_sprite(5, 'earth', 'moth', 'long', 'sit', True), (3.3, 1.55, 8.55), 0.85, soft=True)
    ground_shadow(img, depth, 2.05, 12.0, 0.3, 0.14, 0.3)
    draw_billboard(img, depth, pixie_sprite(6, 'water', 'petal', 'long', 'kneel', False), (2.0, -0.05, 12.0), 0.8, soft=True)

    # 15-bit colour, ordered dither, then the hard-pixel scale-up
    a = np.clip(img, 0, 255)
    yy, xx = np.mgrid[0:RH, 0:RW]
    v = 1 - 0.22 * np.clip(((xx - RW / 2) / (RW * 0.7)) ** 2 + ((yy - RH * 0.5) / (RH * 0.8)) ** 2, 0, 1)
    a = a * v[:, :, None]
    m = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], np.float32) / 16 - 0.5
    tile = np.tile(m, (RH // 4 + 1, RW // 4 + 1))[:RH, :RW][:, :, None]
    step = 255 / 31
    a = np.clip(np.round(a / step + tile) * step, 0, 255).astype(np.uint8)
    return Image.fromarray(a).resize((RW * SCALE, RH * SCALE), Image.NEAREST)


def load_sprites(folder):
    sprites = []
    for f in sorted(Path(folder).expanduser().glob('*.png')):
        im = Image.open(f).convert('RGBA')
        box = im.getbbox()
        if box:
            sprites.append(im.crop(box))
    if not sprites:
        raise SystemExit(f'render-garden: no PNG sprites in {folder}')
    return sprites


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description="Render Avalon's garden wallpaper")
    ap.add_argument('--pixies', help='a folder of your own pixie sprites (PNG, transparent background)')
    ap.add_argument('--out', help='where to write it (required with --pixies; the stock file is left alone)')
    a = ap.parse_args()
    if a.pixies and not a.out:
        ap.error('--pixies needs --out, so the stock wallpaper in the repository is left as it is')
    out = Path(a.out).expanduser() if a.out else OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    render(load_sprites(a.pixies) if a.pixies else None).save(out, optimize=True)
    print('written', out)

#!/usr/bin/env python3
"""render-garden.py: Avalon's wallpaper, rendered as a small 3D scene the way a 1999 console
would have drawn it. Original scene, in the spirit of late-1990s PlayStation garden games:

  - a meadow plateau with a pond, its cut-away earth face towards the camera
  - forest walls of camera-facing billboard pines, distant hills
  - low-poly flat-shaded objects: a boulder with Pasha on it, a crystal prism, floating beacons
  - gourds in their leaves, red bushes, tan mounds and grass tufts, with shadows under things
  - perspective-correct ground with unfiltered (nearest) textures, distance fog,
    480x320, 15-bit colour with ordered dithering, scaled up 6x with hard pixels

    python3 build/render-garden.py        writes desktop/usr/share/avalon/garden-wallpaper.png
"""
import math
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent.parent
OUT = HERE / 'desktop/usr/share/avalon/garden-wallpaper.png'
PASHA = HERE / 'branding/pasha.png'
RW, RH = 480, 320          # the render
SCALE = 6                  # 2880x1920
rng = random.Random(1999)
nrng = np.random.default_rng(1999)

MIST = np.array([168, 166, 190], np.float32)
FOG_NEAR, FOG_FAR = 6.0, 78.0


# ---------------------------------------------------------------- camera
CAM = np.array([0.0, 2.0, 0.0])
PITCH = math.radians(-11)          # looking down a little
FOV = math.radians(62)
F = (RW / 2) / math.tan(FOV / 2)
CX, CY = RW / 2, RH / 2
# camera -> world: a rotation about x by PITCH (forward (0,0,1) goes to (0, sin P, cos P))
_c, _s = math.cos(PITCH), math.sin(PITCH)
R = np.array([[1, 0, 0], [0, _c, _s], [0, -_s, _c]], np.float64)
RT = R.T                           # world -> camera


def project(p):
    """world (x, y, z) -> screen (sx, sy, depth along the view)"""
    cx, cy, cz = RT @ (np.asarray(p, np.float64) - CAM)
    if cz <= 0.05:
        return None
    return (CX + F * cx / cz, CY - F * cy / cz, cz)


def fog_amount(depth):
    return float(np.clip((depth - FOG_NEAR) / (FOG_FAR - FOG_NEAR), 0, 1)) ** 0.9


def fogged(colour, depth):
    a = fog_amount(depth)
    return tuple(int(colour[i] * (1 - a) + MIST[i] * a) for i in range(3))


# --------------------------------------------------------------- textures
def tex(size, base, spread, seed, grain=1.0, levels=5):
    g = np.random.default_rng(seed)
    n = g.random((size, size)).astype(np.float32)
    # blurred with wrap-around, so a tile's edges meet the next tile's without a seam
    big = np.tile(n, (3, 3))
    im = Image.fromarray((big * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(grain))
    n = np.asarray(im).astype(np.float32)[size:2 * size, size:2 * size] / 255
    n = (n - n.min()) / max(1e-6, n.max() - n.min())
    q = np.floor(n * levels) / (levels - 1)
    t = np.zeros((size, size, 3), np.float32)
    for i in range(3):
        t[:, :, i] = base[i] * (1 - spread / 2 + spread * q)
    return np.clip(t, 0, 255)


GRASS = tex(64, (66, 112, 50), 0.75, 1, grain=0.9, levels=6)
GRASS2 = tex(64, (52, 92, 44), 0.6, 4, grain=2.2, levels=4)
WATER = tex(32, (150, 152, 184), 0.18, 2, grain=1.6, levels=4)
SOIL = tex(64, (58, 44, 40), 0.7, 3, grain=1.2, levels=5)


# ------------------------------------------------------- ground and sky (per pixel)
def ground_and_sky():
    ys, xs = np.mgrid[0:RH, 0:RW].astype(np.float32)
    # camera-space ray directions
    dx = (xs - CX) / F
    dy = -(ys - CY) / F
    dz = np.ones_like(dx)
    wx = R[0, 0] * dx + R[0, 1] * dy + R[0, 2] * dz
    wy = R[1, 0] * dx + R[1, 1] * dy + R[1, 2] * dz
    wz = R[2, 0] * dx + R[2, 1] * dy + R[2, 2] * dz

    img = np.zeros((RH, RW, 3), np.float32)
    depth = np.full((RH, RW), 1e9, np.float32)

    # sky: violet-grey above, mist towards the horizon
    elev = np.clip(wy / np.sqrt(wx * wx + wy * wy + wz * wz), -1, 1)
    t = np.clip(elev / 0.45, 0, 1)[:, :, None]
    sky_top, sky_low = np.array([96, 94, 132], np.float32), MIST + np.array([6, 6, 10], np.float32)
    img[:] = sky_low * (1 - t) + sky_top * t

    # the plateau: ground plane y = 0, from the cut-away edge at z = EDGE onwards
    EDGE = 4.0
    with np.errstate(divide='ignore', invalid='ignore'):
        tg = np.where(wy < -1e-4, -CAM[1] / wy, np.inf)
    with np.errstate(invalid='ignore'):
        gx, gz = CAM[0] + wx * tg, CAM[2] + wz * tg
    gx = np.nan_to_num(gx, nan=0, posinf=0, neginf=0); gz = np.nan_to_num(gz, nan=0, posinf=0, neginf=0)
    on_ground = np.isfinite(tg) & (gz >= EDGE)
    # grass: nearest-sampled, tiled every 2 m; a little brighter further off (the mist's light)
    u = np.floor(gx * 32).astype(int) % 64
    v = np.floor(gz * 32).astype(int) % 64
    # two grasses: the fine one, and a coarser darker one in clumps across the meadow
    u2 = np.floor(gx * 20).astype(int) % 64
    v2 = np.floor(gz * 20).astype(int) % 64
    clump = (np.sin(gx * 2.3 + 0.4) + np.sin(gz * 2.9 + gx * 0.9) + np.sin(gx * 1.1 - gz * 1.7)) > 1.6
    grass = np.where(clump[:, :, None], GRASS2[v2, u2], GRASS[v, u])
    shade = np.clip(1.08 - 0.010 * gz, 0.72, 1.08)[:, :, None]
    # large soft patches of light and shadow across the meadow, and the forest's shade at its edge
    patch = (np.sin(gx * 0.31 + 1.3) * np.sin(gz * 0.23) * 0.08 + 1)[:, :, None]
    edge_shade = (1 - 0.35 * np.clip((gz - 20) / 10, 0, 1))[:, :, None]
    gcol = grass * shade * patch * edge_shade
    # the pond: an ellipse holding the sky
    pond = ((gx - 3.6) / 3.8) ** 2 + ((gz - 13.0) / 1.7) ** 2 < 1
    wu = np.floor(gx * 12).astype(int) % 32
    wv = np.floor(gz * 24).astype(int) % 32
    water = WATER[wv, wu] * 0.55 + np.array([60, 66, 96], np.float32) * 0.45
    rim = (((gx - 3.6) / 4.0) ** 2 + ((gz - 13.0) / 1.85) ** 2 < 1) & ~pond
    gcol = np.where(pond[:, :, None], water, gcol)
    stones = ((np.floor(gx * 6) + np.floor(gz * 9)) % 3 == 0)[:, :, None]
    gcol = np.where(rim[:, :, None], np.where(stones, np.array([128, 126, 134], np.float32), np.array([96, 98, 92], np.float32)), gcol)
    img = np.where(on_ground[:, :, None], gcol, img)
    depth = np.where(on_ground, tg, depth)

    # the cut-away face: a vertical wall at z = EDGE, down to y = -6
    with np.errstate(divide='ignore', invalid='ignore'):
        tw = np.where(wz > 1e-4, (EDGE - CAM[2]) / wz, np.inf)
    with np.errstate(invalid='ignore'):
        wyy = np.nan_to_num(CAM[1] + wy * tw, nan=99, posinf=99, neginf=99)
        wxx = np.nan_to_num(CAM[0] + wx * tw, nan=0, posinf=0, neginf=0)
    on_wall = np.isfinite(tw) & (wyy <= 0) & (wyy >= -6) & ~on_ground
    su = np.floor(wxx * 24).astype(int) % 64
    sv = np.floor(-wyy * 24).astype(int) % 64
    soil = SOIL[sv, su] * np.clip(1 + wyy * 0.09, 0.4, 1)[:, :, None]
    # a lip of grass hanging over the top of the face
    # a ragged lip of grass hanging over the top of the face, with roots below it
    lip = wyy > -0.10 - 0.18 * np.abs(np.sin(wxx * 7.3) * np.sin(wxx * 3.1 + 1))
    lipcol = GRASS[sv % 64, su % 64] * 0.7
    soil = np.where(lip[:, :, None], lipcol, soil)
    img = np.where(on_wall[:, :, None], soil, img)
    depth = np.where(on_wall, tw, depth)
    below = ~on_ground & ~on_wall & (wy < 0)
    img = np.where(below[:, :, None], np.array([20, 16, 18], np.float32), img)

    # fog by depth over everything with a depth
    a = np.clip((depth - FOG_NEAR) / (FOG_FAR - FOG_NEAR), 0, 1) ** 0.9
    a = np.where(depth > 1e8, 0, a)[:, :, None]
    img = img * (1 - a) + MIST * a
    return img, depth


# ------------------------------------------------------------- billboards
def pine_sprite(h_px, seed, base):
    """a pine as a texture: ragged tiers filled with clustered needles; RGBA"""
    w_px = int(h_px * 0.55) + 2
    r = random.Random(seed)
    mask = Image.new('L', (w_px, h_px), 0)
    d = ImageDraw.Draw(mask)
    cx = w_px / 2
    d.line([(cx, h_px), (cx, h_px * 0.05)], fill=255, width=max(1, h_px // 40))
    tiers = 6 + h_px // 18
    for t in range(tiers):
        f = t / tiers
        ty = h_px * 0.02 + h_px * f * 0.9
        hw = w_px * (0.08 + 0.42 * f) * r.uniform(0.8, 1.1)
        drop = h_px * 0.13
        pts = [(cx, ty)] + [(cx + hw * (-1 + k / 2.5), ty + drop * (0.7 + 0.4 * r.random())) for k in range(6)]
        d.polygon(pts, fill=255)
    t = tex(max(w_px, h_px), base, 0.6, seed, grain=0.7, levels=5)[:h_px, :w_px]
    # light from the left: the left half a shade brighter
    t[:, : w_px // 2] *= 1.12
    rgba = np.dstack([np.clip(t, 0, 255).astype(np.uint8), np.asarray(mask)])
    return Image.fromarray(rgba, 'RGBA')


def draw_billboard(img, depthbuf, sprite, world_base, height_m):
    """a sprite standing at world_base, height_m tall, depth-tested per pixel, fogged"""
    p = project(world_base)
    if not p:
        return
    sx, sy, z = p
    hp = int(F * height_m / z)
    if hp < 2:
        return
    wp = max(1, int(hp * sprite.width / sprite.height))
    spr = sprite.resize((wp, hp), Image.NEAREST)
    a = np.asarray(spr).astype(np.float32)
    col = a[:, :, :3]
    fa = fog_amount(z)
    col = col * (1 - fa) + MIST * fa
    x0, y0 = int(sx - wp / 2), int(sy - hp)
    xa, ya = max(0, x0), max(0, y0)
    xb, yb = min(RW, x0 + wp), min(RH, y0 + hp)
    if xa >= xb or ya >= yb:
        return
    sub_a = a[ya - y0:yb - y0, xa - x0:xb - x0, 3] > 128
    sub_c = col[ya - y0:yb - y0, xa - x0:xb - x0]
    nearer = depthbuf[ya:yb, xa:xb] > z
    m = sub_a & nearer
    img[ya:yb, xa:xb][m] = sub_c[m]
    depthbuf[ya:yb, xa:xb][m] = z


# ------------------------------------------------------- low-poly objects
def draw_mesh(img, depthbuf, verts, faces, colour, light=(-0.6, 0.7, -0.4), alpha=1.0, edges=None, cull=True):
    """flat-shaded polygons, painter-sorted, fogged; optional glowing edge colour"""
    L = np.array(light) / np.linalg.norm(light)
    pv = [project(v) for v in verts]
    order = []
    for f in faces:
        if any(pv[i] is None for i in f):
            continue
        a, b, c = (np.array(verts[i]) for i in f[:3])
        n = np.cross(b - a, c - a)
        nn = np.linalg.norm(n)
        if nn == 0:
            continue
        n /= nn
        centre = np.mean([verts[i] for i in f], axis=0)
        to_cam = CAM - centre
        if np.dot(n, to_cam) <= 0:      # facing away
            if cull:
                continue
            n = -n
        z = np.mean([pv[i][2] for i in f])
        lum = 0.45 + 0.55 * max(0, float(np.dot(n, L)))
        order.append((z, f, lum))
    order.sort(key=lambda o: -o[0])
    layer = Image.new('RGBA', (RW, RH), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    zmin = 1e9
    for z, f, lum in order:
        c = fogged(tuple(min(255, int(ch * lum)) for ch in colour), z)
        pts = [(round(pv[i][0]), round(pv[i][1])) for i in f]   # snapped to whole pixels, as the console did
        d.polygon(pts, fill=c + (int(255 * alpha),))
        if edges:
            d.line(pts + [pts[0]], fill=edges + (255,), width=1)
        zmin = min(zmin, z)
    arr = np.asarray(layer).astype(np.float32)
    m = (arr[:, :, 3] > 0) & (depthbuf > zmin)
    a = (arr[:, :, 3:4] / 255)
    img[m] = (img * (1 - a) + arr[:, :, :3] * a)[m]
    depthbuf[m] = np.minimum(depthbuf[m], zmin)


def octahedron(c, r, h):
    x, y, z = c
    v = [(x, y + h, z), (x + r, y, z), (x, y, z + r), (x - r, y, z), (x, y, z - r), (x, y - h, z)]
    f = [(0, 2, 1), (0, 3, 2), (0, 4, 3), (0, 1, 4), (5, 1, 2), (5, 2, 3), (5, 3, 4), (5, 4, 1)]
    return v, f


def prism(c, r, h, sides=6):
    x, y, z = c
    v = []
    for k in range(sides):
        a = 2 * math.pi * k / sides
        v.append((x + r * math.cos(a), y, z + r * math.sin(a)))
    for k in range(sides):
        a = 2 * math.pi * k / sides
        v.append((x + r * math.cos(a), y + h, z + r * math.sin(a)))
    v.append((x, y + h + r * 1.1, z))
    f = [(k, (k + 1) % sides, sides + (k + 1) % sides, sides + k) for k in range(sides)]
    f += [(sides + k, sides + (k + 1) % sides, 2 * sides) for k in range(sides)]
    return v, f


def rock(c, s):
    """a boulder: a jittered, flattened ring of faces under a lumpy top"""
    x, y, z = c
    r = random.Random(7)
    n = 9
    base = [(x + s * 1.15 * math.cos(2 * math.pi * k / n) * r.uniform(0.85, 1.1), y,
             z + s * 0.85 * math.sin(2 * math.pi * k / n) * r.uniform(0.85, 1.1)) for k in range(n)]
    mid = [(x + s * 0.95 * math.cos(2 * math.pi * (k + 0.5) / n) * r.uniform(0.85, 1.05), y + s * r.uniform(0.38, 0.5),
            z + s * 0.7 * math.sin(2 * math.pi * (k + 0.5) / n) * r.uniform(0.85, 1.05)) for k in range(n)]
    top = (x, y + s * 0.62, z)
    v = base + mid + [top]
    f = []
    for k in range(n):
        f.append((k, (k + 1) % n, n + k))
        f.append(((k + 1) % n, n + (k + 1) % n, n + k))
        f.append((n + k, n + (k + 1) % n, 2 * n))
    return v, f


def sprite_pasha():
    p = Image.open(PASHA).convert('RGBA')
    bbox = p.getbbox()
    p = p.crop(bbox)
    small = p.resize((int(p.width * 96 / p.height), 96), Image.LANCZOS)
    rgb = small.convert('RGB').quantize(colors=12, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).convert('RGB')
    rgb = Image.fromarray((np.asarray(rgb).astype(np.float32) * np.array([0.86, 0.88, 0.97])).astype(np.uint8))
    a = small.split()[3].point(lambda v: 255 if v > 110 else 0)
    out = rgb.convert('RGBA')
    out.putalpha(a)
    return out


def gourd_sprite(seed):
    """an orange, spotted gourd sitting in broad leaves"""
    r = random.Random(seed)
    s = Image.new('RGBA', (60, 50), (0, 0, 0, 0))
    d = ImageDraw.Draw(s)

    def leaf(a, length, shade):
        ex, ey = 30 + math.cos(a) * length, 44 + math.sin(a) * length * 0.3
        nx, ny = -math.sin(a) * 8, math.cos(a) * 4
        c = (int(96 * shade), int(158 * shade), int(58 * shade), 255)
        pts = [(30, 44), (30 + (ex - 30) * 0.5 + nx, 44 + (ey - 44) * 0.5 + ny), (ex, ey),
               (30 + (ex - 30) * 0.5 - nx, 44 + (ey - 44) * 0.5 - ny)]
        d.polygon(pts, fill=c, outline=(34, 70, 28, 255))
        d.line([(30, 44), (ex, ey)], fill=(int(140 * shade), int(196 * shade), 92, 255))
    for k in range(5):                                  # leaves behind
        leaf(math.radians(185 + k * 42 + r.uniform(-8, 8)), r.uniform(24, 29), 0.78)
    d.ellipse([13, 16, 47, 46], fill=(176, 96, 28, 255))   # the body, its shaded underside
    d.ellipse([14, 15, 44, 41], fill=(214, 128, 40, 255))
    d.ellipse([17, 16, 34, 32], fill=(240, 166, 66, 255))  # its lit side
    for x0, bend in ((22, -2), (30, 0), (38, 2)):          # ribs
        d.line([(x0, 17), (x0 + bend, 30), (x0, 44)], fill=(160, 84, 26, 255), width=1)
    for _ in range(16):                                 # spots
        x, y = r.uniform(16, 44), r.uniform(19, 42)
        d.rectangle([x, y, x + 1, y + 1], fill=(112, 58, 24, 255))
    d.polygon([(29, 10), (32, 10), (31, 17), (29, 17)], fill=(96, 120, 52, 255))  # stalk
    for a in (15, 70, 115, 165):                         # leaves in front, low and spreading
        leaf(math.radians(a + r.uniform(-8, 8)), r.uniform(20, 27), 1.0)
    return s


def bush_sprite(seed):
    """a low red-leaved bush"""
    r = random.Random(seed)
    s = Image.new('RGBA', (52, 40), (0, 0, 0, 0))
    d = ImageDraw.Draw(s)
    for _ in range(60):
        x, y = r.gauss(26, 10), r.gauss(24, 7)
        rr = r.uniform(2, 4)
        c = r.choice([(150, 40, 32), (186, 58, 40), (214, 86, 52), (120, 30, 30)])
        d.ellipse([x - rr, y - rr * 0.7, x + rr, y + rr * 0.7], fill=c + (255,))
    return s


def mound_sprite(seed):
    """a cluster of small tan cones, like termite mounds or puffballs"""
    r = random.Random(seed)
    s = Image.new('RGBA', (44, 34), (0, 0, 0, 0))
    d = ImageDraw.Draw(s)
    for cx, h, w in ((14, 28, 9), (28, 20, 8), (36, 13, 6)):
        d.polygon([(cx - w, 33), (cx, 33 - h), (cx + w, 33)], fill=(186, 150, 104, 255))
        d.polygon([(cx, 33 - h), (cx + w, 33), (cx + 1, 33)], fill=(146, 112, 76, 255))
        for _ in range(h // 3):
            y = r.uniform(33 - h * 0.8, 32); x = cx + r.uniform(-w, w) * (33 - y) / h * 0.9
            d.point((x, y), fill=(110, 82, 56, 255))
    return s


def tuft_sprite(seed):
    r = random.Random(seed)
    s = Image.new('RGBA', (30, 30), (0, 0, 0, 0))
    d = ImageDraw.Draw(s)
    for _ in range(16):
        x = r.uniform(4, 26)
        d.line([(15, 30), (x, r.uniform(2, 14))], fill=(78 + r.randrange(40), 130 + r.randrange(40), 60, 255), width=1)
    return s


def ground_shadow(img, depthbuf, x, z, rx, rz, strength=0.45):
    """a soft dark patch on the meadow under something standing (or floating) at (x, z)"""
    pts = [project((x + rx * math.cos(t), 0.0, z + rz * math.sin(t))) for t in np.linspace(0, 2 * math.pi, 24)]
    if any(p is None for p in pts):
        return
    layer = Image.new('L', (RW, RH), 0)
    ImageDraw.Draw(layer).polygon([(p[0], p[1]) for p in pts], fill=255)
    m = np.asarray(layer.filter(ImageFilter.GaussianBlur(1.2))).astype(np.float32) / 255
    m *= (depthbuf > z - rz * 2)                  # on the ground, not over nearer things
    img *= (1 - strength * m)[:, :, None]


def bubble_sprite():
    s = Image.new('RGBA', (40, 40), (0, 0, 0, 0))
    d = ImageDraw.Draw(s)
    d.ellipse([1, 1, 38, 38], fill=(178, 204, 240, 150), outline=(226, 238, 255, 255))
    d.ellipse([10, 9, 22, 21], fill=(238, 234, 250, 255))
    d.ellipse([13, 16, 30, 32], fill=(210, 202, 236, 255))
    d.polygon([(21, 18), (34, 8), (28, 24)], fill=(190, 230, 250, 255))
    d.ellipse([6, 5, 14, 11], fill=(255, 255, 255, 255))
    return s


# ----------------------------------------------------------------- scene
def render():
    img, depth = ground_and_sky()

    # distant hills: a band of billboards far off, nearly lost in the mist
    hill = Image.new('RGBA', (400, 60), (0, 0, 0, 0))
    hd = ImageDraw.Draw(hill)
    hd.polygon([(0, 60)] + [(x, 30 - 14 * math.sin(x / 40) - 8 * math.sin(x / 13)) for x in range(0, 404, 4)] + [(400, 60)], fill=(120, 120, 150, 255))
    for x in (-160, 0, 160):
        draw_billboard(img, depth, hill, (x, 0, 140), 26)

    # forest walls: rows of pines, the furthest first; a gap to the right where the meadow opens
    pines = [pine_sprite(160, s, (r, g, b)) for s, (r, g, b) in enumerate([(40, 62, 46), (48, 72, 52), (34, 56, 40), (56, 80, 58)])]
    trees = []
    for row, (zmin, zmax, count) in enumerate([(52, 62, 90), (40, 48, 70), (30, 35, 46)]):
        for _ in range(count):
            x = rng.uniform(-40, 40)
            z = rng.uniform(zmin, zmax)
            trees.append((z, x, rng.uniform(6.5, 10.5)))
    # a few nearer trees at the sides, framing the clearing
    for x, z, h in ((-10, 14, 9), (-13, 19, 10), (-8.5, 10, 7.5), (12, 17, 9.5), (14.5, 23, 10), (10, 12, 7.5)):
        trees.append((z, x, h))
    trees.sort(key=lambda t: -t[0])
    for z, x, h in trees:
        draw_billboard(img, depth, pines[rng.randrange(len(pines))], (x, 0, z), h)

    # light falling through the mist
    shafts = Image.new('RGBA', (RW, RH), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shafts)
    for x0, wd in ((70, 30), (150, 18), (300, 40), (370, 22)):
        sd.polygon([(x0, 0), (x0 + wd, 0), (x0 + wd * 2 - 60, RH * 0.6), (x0 + wd - 80, RH * 0.6)], fill=(232, 232, 248, 30))
    sh = np.asarray(shafts.filter(ImageFilter.GaussianBlur(6))).astype(np.float32)
    img = img * (1 - sh[:, :, 3:4] / 255) + sh[:, :, :3] * (sh[:, :, 3:4] / 255)

    # plants of the garden: gourds in their leaves, red bushes, tan mounds, tufts of grass
    plants = ((-5.6, 14.0, 1.0, bush_sprite(1)), (6.2, 16.5, 1.1, bush_sprite(2)), (-6.4, 19.5, 0.9, bush_sprite(8)),
              (-2.9, 12.6, 0.5, mound_sprite(3)), (2.7, 6.2, 0.42, mound_sprite(6)),
              (-3.3, 7.0, 0.85, gourd_sprite(4)), (4.7, 11.6, 0.9, gourd_sprite(5)), (-1.7, 5.4, 0.6, gourd_sprite(9)))
    for x, z, h, spr in plants:
        ground_shadow(img, depth, x, z, h * 0.55, h * 0.3, 0.35)
    for x, z, h, spr in sorted(plants, key=lambda p: -p[1]):
        draw_billboard(img, depth, spr, (x, 0, z), h)
    for k in range(26):
        x, z = rng.uniform(-6, 6), rng.uniform(4.6, 18)
        draw_billboard(img, depth, tuft_sprite(k), (x, 0, z), rng.uniform(0.2, 0.32))

    # the crystal prism, violet, on the meadow
    ground_shadow(img, depth, -2.0, 9.05, 0.55, 0.35)
    v, f = prism((-2.1, 0, 9.0), 0.36, 1.8)
    draw_mesh(img, depth, v, f, (168, 142, 226), alpha=0.86, edges=(122, 102, 176))

    # pixies asleep in bubbles
    bub = bubble_sprite()
    ground_shadow(img, depth, -0.45, 8.0, 0.4, 0.22, 0.3)
    ground_shadow(img, depth, 0.42, 7.3, 0.25, 0.14, 0.3)
    draw_billboard(img, depth, bub, (-0.5, 0.1, 8.0), 0.8)
    draw_billboard(img, depth, bub, (0.4, 0.0, 7.3), 0.5)

    # Pasha on his rock, beside the pond
    ground_shadow(img, depth, 2.0, 8.6, 1.25, 0.8)
    v, f = rock((1.9, 0, 8.6), 0.9)
    draw_mesh(img, depth, v, f, (142, 140, 150))
    draw_billboard(img, depth, sprite_pasha(), (1.85, 0.40, 8.55), 1.55)

    # the beacons: solid dark octahedra floating over the meadow, a red band and jewel at the
    # waist, four cyan blades sweeping out from it, and a short spike above and below
    for c, r in (((-3.8, 3.0, 11.5), 0.40), ((5.6, 2.8, 15.0), 0.36)):
        ground_shadow(img, depth, c[0], c[2], r * 1.1, r * 0.7, 0.28)
        v, f = octahedron(c, r, r * 1.5)
        draw_mesh(img, depth, v, f, (44, 44, 58))
        p = project(c)
        if not p:
            continue
        x, y, z = p
        s_ = F * r / z                     # the beacon's half-width on screen
        layer = Image.new('RGBA', (RW, RH), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        # spikes
        h = s_ * 1.5
        d.line([(x, y - h), (x, y - h * 1.35)], fill=(20, 20, 28, 255), width=2)
        d.line([(x, y + h), (x, y + h * 1.35)], fill=(20, 20, 28, 255), width=2)
        # the red band and jewel
        d.line([(x - s_ * 0.92, y), (x + s_ * 0.92, y)], fill=(196, 34, 44, 255), width=max(1, int(s_ * 0.18)))
        d.polygon([(x, y - s_ * 0.22), (x + s_ * 0.2, y), (x, y + s_ * 0.22), (x - s_ * 0.2, y)], fill=(255, 70, 82, 255))
        # four blades: each a thin crescent from near the waist, out and away
        for sx in (-1, 1):
            for sy in (-1, 1):
                p0 = (x + sx * s_ * 0.55, y + sy * s_ * 0.35)
                p1 = (x + sx * s_ * 1.25, y + sy * s_ * 1.05)
                p2 = (x + sx * s_ * 1.55, y + sy * s_ * 1.75)
                q1 = (x + sx * s_ * 0.95, y + sy * s_ * 1.25)
                d.polygon([p0, p1, p2, q1], fill=(110, 226, 246, 255))
                d.line([p0, p1, p2], fill=(210, 250, 255, 255), width=1)
        arr = np.asarray(layer).astype(np.float32)
        fa = fog_amount(z)
        m = arr[:, :, 3] > 0
        img[m] = (arr[:, :, :3] * (1 - fa) + MIST * fa)[m]

    # sparks drifting in the mist
    out = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert('RGBA')
    glow = Image.new('RGBA', (RW, RH), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for c in [(95, 216, 240), (255, 63, 164), (232, 196, 110), (120, 220, 120)] * 3:
        x, y = rng.uniform(40, RW - 40), rng.uniform(90, 210)
        gd.ellipse([x - 3, y - 3, x + 3, y + 3], fill=c + (70,))
        gd.rectangle([x - 1, y - 1, x, y], fill=c + (255,))
    out.alpha_composite(glow)

    # vignette, 15-bit colour, ordered dither, then the hard-pixel scale-up
    a = np.asarray(out.convert('RGB')).astype(np.float32)
    yy, xx = np.mgrid[0:RH, 0:RW]
    v = 1 - 0.38 * np.clip(((xx - RW / 2) / (RW * 0.62)) ** 2 + ((yy - RH * 0.45) / (RH * 0.72)) ** 2, 0, 1)
    a *= v[:, :, None]
    m = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], np.float32) / 16 - 0.5
    tile = np.tile(m, (RH // 4 + 1, RW // 4 + 1))[:RH, :RW][:, :, None]
    step = 255 / 31
    a = np.clip(np.round(a / step + tile) * step, 0, 255).astype(np.uint8)
    return Image.fromarray(a).resize((RW * SCALE, RH * SCALE), Image.NEAREST)


if __name__ == '__main__':
    OUT.parent.mkdir(parents=True, exist_ok=True)
    render().save(OUT, optimize=True)
    print('written', OUT)

# Builds the exterior (our building, the ochre block on the left, the block on the right) from the street photos and bakes
# ambient occlusion + weathering into a second UV set:
#   blender -b --factory-startup --python tools/bake/building.py -- <out dir> [map size] [samples]
# Output: building.glb (one mesh, materials by name, TEXCOORD_0 = plaster UVs in 5.5 m tiles, TEXCOORD_1 = bake UVs)
#         building_ao.png (AO x grime, linear, multiplies the diffuse colour in the site)
# Coordinates are the site's scene coordinates (x east, y up, z towards the square; our facade at z = 0).
# Parts the site keeps procedural (shop front, entrance recess, lobby, the flat's own wall) are left out here.
import bpy, bmesh, sys, math, os, random
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index('--') + 1:]
OUT = argv[0]
SIZE = int(argv[1]) if len(argv) > 1 else 4096
SAMPLES = int(argv[2]) if len(argv) > 2 else 64
os.makedirs(OUT, exist_ok=True)

G, TOP, FX0, FX1, BD, FL = 2.88, 8.7, -16.0, 30.0, 12.0, 2.91
OX0, OX1, OZ0, OZ1, OH = -40.0, -16.0, -14.0, -3.0, 17.4       # ochre neighbour
TILE = 5.5

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene

COL = {   # preview colours only: the site assigns its own materials by name
    'wall': (0.80, 0.77, 0.70), 'ochre': (0.80, 0.62, 0.36), 'deck': (0.45, 0.44, 0.42), 'frame': (0.92, 0.92, 0.90),
    'glass': (0.20, 0.25, 0.30), 'glassLit': (0.20, 0.25, 0.30), 'room': (0.05, 0.05, 0.05), 'roomLit': (0.06, 0.05, 0.04), 'curtain': (0.80, 0.78, 0.72),
    'curtainLit': (0.82, 0.78, 0.70), 'blind': (0.85, 0.86, 0.87), 'sill': (0.45, 0.46, 0.47), 'metal': (0.18, 0.19, 0.20),
    'roof': (0.32, 0.16, 0.10), 'plinth': (0.40, 0.45, 0.52), 'ac': (0.78, 0.79, 0.80), 'grille': (0.10, 0.10, 0.11),
}
NAMES = list(COL)
MI = {n: i for i, n in enumerate(NAMES)}
bm = bmesh.new()

def tb(p): return (p[0], -p[2], p[1])          # three -> Blender (a rotation, so face winding is kept)

class Frame:                                   # local facade frame: u along the facade, v up, w out of the wall
    def __init__(self, o, u, n): self.o, self.u, self.n = Vector(o), Vector(u), Vector(n)
    def p(self, u, v, w): return self.o + self.u * u + Vector((0, 1, 0)) * v + self.n * w
WORLD = Frame((0, 0, 0), (1, 0, 0), (0, 0, 1))

FACES = {'w0': (0, 3, 2, 1), 'w1': (4, 5, 6, 7), 'v0': (0, 1, 5, 4), 'v1': (3, 7, 6, 2), 'u0': (0, 4, 7, 3), 'u1': (1, 2, 6, 5)}
def hexa(pts, m, skip=(), mats=None):
    vs = [bm.verts.new(tb(p)) for p in pts]
    for k, ix in FACES.items():
        if k in skip: continue
        f = bm.faces.new([vs[i] for i in ix]); f.material_index = MI[(mats or {}).get(k, m)]
def box(F, u0, u1, v0, v1, w0, w1, m, skip=(), mats=None):
    hexa([F.p(u, v, w) for (u, v, w) in [(u0, v0, w0), (u1, v0, w0), (u1, v1, w0), (u0, v1, w0),
                                          (u0, v0, w1), (u1, v0, w1), (u1, v1, w1), (u0, v1, w1)]], m, skip, mats)
def quad(F, u0, u1, v0, v1, w, m):             # faces +w
    f = bm.faces.new([bm.verts.new(tb(F.p(u, v, w))) for (u, v) in [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]]); f.material_index = MI[m]
def tube(F, u, v0, v1, w, r, m, seg=8):        # vertical pipe
    ring = lambda v: [bm.verts.new(tb(F.p(u + r * math.cos(a), v, w + r * math.sin(a)))) for a in [i / seg * 6.2832 for i in range(seg)]]
    a, b = ring(v0), ring(v1)
    for i in range(seg):
        j = (i + 1) % seg; f = bm.faces.new([a[i], b[i], b[j], a[j]]); f.material_index = MI[m]; f.smooth = True

# ---------- one window in a wall opening: reveal is the wall, then frame, glass, what is behind it ----------
def window(F, u0, u1, v0, v1, T, rng, lit_p=0.33, ac_p=0.12, shop=False):
    lit = rng.random() < lit_p
    w, h = u1 - u0, v1 - v0
    quad(F, u0, u1, v0, v1, -T, 'roomLit' if lit else 'room')
    if not shop:
        r = rng.random()
        if r < 0.45:                              # curtains, one or both sides
            cm = 'curtainLit' if lit else 'curtain'
            quad(F, u0, u0 + w * rng.uniform(0.18, 0.42), v0, v1, -T + 0.06, cm)
            if rng.random() < 0.6: quad(F, u1 - w * rng.uniform(0.18, 0.42), u1, v0, v1, -T + 0.06, cm)
        elif r < 0.55:
            quad(F, u0, u1, v0, v1, -T + 0.06, 'curtainLit' if lit else 'curtain')   # net curtain across
    t, d0, d1 = 0.06, -0.16, -0.09
    box(F, u0, u1, v0, v0 + t, d0, d1, 'frame', ('w0',)); box(F, u0, u1, v1 - t, v1, d0, d1, 'frame', ('w0',))
    box(F, u0, u0 + t, v0 + t, v1 - t, d0, d1, 'frame', ('w0', 'v0', 'v1')); box(F, u1 - t, u1, v0 + t, v1 - t, d0, d1, 'frame', ('w0', 'v0', 'v1'))
    if shop:
        for k in range(1, int(w / 1.3) + 1): uu = u0 + k * w / (int(w / 1.3) + 1); box(F, uu - 0.03, uu + 0.03, v0 + t, v1 - t, d0, d1, 'metal', ('w0', 'v0', 'v1'))
    else:
        if w > 0.75: box(F, (u0 + u1) / 2 - 0.035, (u0 + u1) / 2 + 0.035, v0 + t, v1 - t, d0, d1, 'frame', ('w0', 'v0', 'v1'))
        if h > 1.1 and rng.random() < 0.6: box(F, u0 + t, u1 - t, v1 - h * 0.3 - 0.03, v1 - h * 0.3 + 0.03, d0, d1, 'frame', ('w0', 'u0', 'u1'))
    quad(F, u0 + t, u1 - t, v0 + t, v1 - t, -0.125, 'glassLit' if lit else 'glass')
    if not shop:
        if rng.random() < 0.22:                   # roller shutter, partly down
            bh = h * rng.uniform(0.2, 0.75)
            box(F, u0 + 0.02, u1 - 0.02, v1 - bh, v1 - 0.02, -0.08, -0.06, 'blind', ('w0',))
        box(F, u0 - 0.05, u1 + 0.05, v0 - 0.035, v0, -0.12, 0.05, 'sill', ('w0',))           # metal sill
        if rng.random() < ac_p and v0 > 1.2:      # air-conditioner on the wall under the window
            cu = rng.uniform(u0, max(u0, u1 - 0.8))
            box(F, cu, cu + 0.8, v0 - 0.75, v0 - 0.2, 0, 0.28, 'ac', ('w0',))
            quad(F, cu + 0.08, cu + 0.5, v0 - 0.68, v0 - 0.27, 0.281, 'grille')

# ---------- a wall slab with window openings (rows of windows sharing v0/v1), built from bands and piers ----------
def facade(F, L, vb, vt, rows, T, m, rng, ends=(True, True), **wk):
    prev = vb
    for row in sorted(rows, key=lambda r: r[0][2]):
        v0, v1 = row[0][2], row[0][3]
        sk = ['w0'] + (['u0'] if not ends[0] else []) + (['u1'] if not ends[1] else [])
        box(F, 0, L, prev, v0, -T, 0, m, sk)
        u = 0
        for (a, b, _, _, *opt) in sorted(row):
            if a > u + 1e-4: box(F, u, a, v0, v1, -T, 0, m, ['w0', 'v0', 'v1'] + (['u0'] if u == 0 and not ends[0] else []))
            window(F, a, b, v0, v1, T, rng, **{**wk, **(opt[0] if opt else {})}); u = b
        if u < L - 1e-4: box(F, u, L, v0, v1, -T, 0, m, ['w0', 'v0', 'v1'] + (['u1'] if not ends[1] else []))
        prev = v1
    box(F, 0, L, prev, vt, -T, 0, m, ['w0'] + (['u0'] if not ends[0] else []) + (['u1'] if not ends[1] else []))

def ribbon(L, seed, start=1.3):                  # the photo's window bands: groups of 3-4 narrow windows, wider piers between
    r = random.Random(seed); out, gaps = [], []; x, bay = start, 0
    while x < L - 3.6:
        cnt = 4 if bay % 3 == 1 else 3
        for k in range(cnt): out.append((x + k * 1.12, x + k * 1.12 + 0.95))
        x2 = x + cnt * 1.12; g = 1.5 + r.random() * 1.3; gaps.append((x2 - 0.17, x2 - 0.17 + g)); x = x2 + g; bay += 1
    return out, gaps

rng = random.Random(7)

# ===== our building =====
F = Frame((FX0, 0, 0), (1, 0, 0), (0, 0, 1))
cols, gaps = ribbon(FX1 - FX0, 3)
rows = [[(a, b, G + f * FL + 0.85, G + f * FL + 0.85 + 1.32) for a, b in cols] for f in range(2)]
facade(F, FX1 - FX0, G, TOP, rows, 0.42, 'wall', rng, ends=(True, False))
# ground floor walls (shop front, entrance and the flat's wall stay in the site)
def gseg(x0, x1, wins, ends=(True, True), plinth=True):
    Fs = Frame((x0, 0, 0), (1, 0, 0), (0, 0, 1)); L = x1 - x0
    facade(Fs, L, 0, G, [[(a - x0, b - x0, 1.0, 2.2) for a, b in wins]] if wins else [], 0.3, 'wall', rng, ends=ends, lit_p=0.25, ac_p=0)
    if plinth:
        for a, b in ([(x0, x1)] if not wins else [(x0, x1)]): box(WORLD, a, b, 0, 0.9, 0, 0.06, 'plinth', ('w0',))
gseg(FX0, -14.9, [], ends=(True, True))
gseg(-3.0, -1.8, [])
gseg(1.8, 3.91, [(2.25, 3.45)], ends=(True, False))
gseg(8.03, FX1, [(9.2 + i * 3.4, 10.6 + i * 3.4) for i in range(6)], ends=(False, False))
box(WORLD, -14.9, -3.0, G - 0.55, G, -0.3, 0, 'wall', ('w0',))      # lintel over the shop front
box(WORLD, 3.91, 8.03, G - 0.12, G, -0.3, 0, 'wall', ('w0', 'u0', 'u1'))     # lintel over the flat's own wall
box(WORLD, 3.91, 8.03, 0, 0.9, 0, 0.06, 'plinth', ('w0',))
# body behind the slabs: side wall, roof deck
box(WORLD, FX0, FX1, G, TOP, -BD, -0.42, 'wall', ('w0', 'w1', 'u0', 'u1', 'v0'), {'v1': 'deck'})
box(WORLD, FX0, FX0 + 0.3, 0, TOP, OZ1 - 0.35, -0.3, 'wall', ('w1', 'u1', 'v1', 'v0', 'w0'))   # the bit of side wall the ochre block leaves visible
# cornice, parapet, railing, roof clutter
box(WORLD, FX0 - 0.05, FX1, TOP - 0.16, TOP, 0, 0.07, 'wall', ('w0',))
box(WORLD, FX0, FX1, TOP, TOP + 0.45, -0.25, 0.03, 'wall', ('u1',))
box(WORLD, FX0, FX0 + 0.25, TOP, TOP + 0.45, -BD, -0.25, 'wall', ('w1',))
box(WORLD, FX0, FX1, TOP, TOP + 0.45, -BD, -BD + 0.25, 'wall', ('w0',))
x = FX0 + 0.4
while x < FX1:
    box(WORLD, x - 0.025, x + 0.025, TOP + 0.45, TOP + 1.35, -0.15, -0.1, 'metal'); x += 2.0
for y in (TOP + 0.95, TOP + 1.35): box(WORLD, FX0 + 0.3, FX1, y - 0.025, y + 0.025, -0.16, -0.09, 'metal')
for cx, cz, ch in [(-11.2, -3.0, 1.5), (-4.6, -3.6, 1.9), (2.8, -2.6, 1.4), (10.4, -3.2, 1.8), (16.9, -2.8, 1.5), (24.3, -3.4, 1.7), (-8.0, -8.5, 1.3), (20.0, -9.0, 1.3)]:
    box(WORLD, cx - 0.38, cx + 0.38, TOP, TOP + ch, cz - 0.38, cz + 0.38, 'wall', ('v0',))
    box(WORLD, cx - 0.46, cx + 0.46, TOP + ch, TOP + ch + 0.06, cz - 0.46, cz + 0.46, 'sill')
    for sx in (-0.3, 0.3): box(WORLD, cx + sx - 0.04, cx + sx + 0.04, TOP + ch + 0.06, TOP + ch + 0.3, cz - 0.04, cz + 0.04, 'metal')
    box(WORLD, cx - 0.5, cx + 0.5, TOP + ch + 0.3, TOP + ch + 0.36, cz - 0.5, cz + 0.5, 'sill')
box(WORLD, 4.5, 7.5, TOP, TOP + 2.3, -7.5, -5.0, 'wall', ('v0',), {'v1': 'deck'})          # stair housing on the roof
box(WORLD, 5.5, 6.4, TOP, TOP + 2.0, -5.0, -4.97, 'metal', ('v0', 'w0'))
for ax, az in [(1.5, -4.5), (11.0, -5.5), (19.5, -6.0), (-6.5, -5.0)]: box(WORLD, ax - 0.45, ax + 0.45, TOP, TOP + 0.6, az - 0.3, az + 0.3, 'ac', ('v0',))
# downpipes in a few of the wider piers (only where the ground floor is wall)
for i, (a, b) in enumerate(gaps):
    px = FX0 + (a + b) / 2
    clear = all(px < 9.05 + k * 3.4 or px > 10.75 + k * 3.4 for k in range(6))   # keep off the ground-floor windows
    if i % 3 == 1 and clear and (px > 8.4 or 2.0 < px < 3.7): tube(WORLD, px, 0.1, TOP + 0.05, 0.08, 0.05, 'sill')

# ===== ochre block on the left (6 storeys, tiled hip, front z = -3) =====
Fo = Frame((OX0, 0, OZ1), (1, 0, 0), (0, 0, 1))
ocols = []; u = 1.0
while u < (OX1 - OX0) - 2.5: ocols += [(u, u + 1.25), (u + 1.5, u + 2.75)]; u += 4.3
orows = [[(a, b, f * 2.9 + 0.85, f * 2.9 + 0.85 + 1.4) for a, b in ocols] for f in range(1, 6)]
orows.append([(a, a + 3.6, 0.25, 2.6, {'shop': True, 'lit_p': 0.7}) for a in (1.0, 5.6, 10.2, 14.8, 19.4)])
facade(Fo, OX1 - OX0, 0, OH, orows, 0.35, 'ochre', rng, ends=(True, False), ac_p=0.25, lit_p=0.3)
Fs = Frame((OX1, 0, OZ1), (0, 0, -1), (1, 0, 0))                     # side facing our roof: windows only above it
srows = [[(a, b, f * 2.9 + 0.85, f * 2.9 + 0.85 + 1.4) for a, b in [(1.6, 2.85), (3.1, 4.35), (6.6, 7.85)]] for f in range(3, 6)]
facade(Fs, OZ1 - OZ0, TOP - 0.2, OH, srows, 0.35, 'ochre', rng, ac_p=0.25, lit_p=0.3)
box(WORLD, OX0, OX0 + 0.35, 0, OH, OZ0, OZ1 - 0.35, 'ochre', ('u1', 'v0', 'v1', 'w0', 'w1'))
for f in range(1, 6): box(Fo, 0, OX1 - OX0, f * 2.9 - 0.02, f * 2.9 + 0.1, 0, 0.04, 'ochre', ('w0',))   # slab lines
box(Fo, -0.1, OX1 - OX0 + 0.1, OH - 0.2, OH, 0, 0.35, 'ochre', ('w0',))
# hip roof: two sloped slabs with an overhang + gable walls
yE, yR, zR = OH - 0.15, OH + 3.6, (OZ0 + OZ1) / 2
def slope(z_out, s_out_is_front):
    pts = []
    for (uu, tt, ss) in [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]:
        x = OX0 - 0.45 + uu * (OX1 - OX0 + 0.9)
        if s_out_is_front: y, z = yR + (yE - yR) * ss, zR + (z_out - zR) * ss
        else: y, z = yE + (yR - yE) * ss, z_out + (zR - z_out) * ss
        pts.append((x, y + tt * 0.16, z))
    hexa(pts, 'roof', mats={'v0': 'ochre'})
slope(OZ1 + 0.55, True); slope(OZ0 - 0.55, False)
for gx, sgn in [(OX1, 1), (OX0, -1)]:
    a, b, c = bm.verts.new(tb((gx, OH, OZ1))), bm.verts.new(tb((gx, OH, OZ0))), bm.verts.new(tb((gx, yR, zR)))
    f = bm.faces.new([a, b, c] if sgn > 0 else [c, b, a]); f.material_index = MI['ochre']
for cx in (-36.0, -29.0, -22.0):
    box(WORLD, cx - 0.35, cx + 0.35, yR - 0.8, yR + 1.0, zR - 0.35, zR + 0.35, 'ochre', ('v0',))
    box(WORLD, cx - 0.43, cx + 0.43, yR + 1.0, yR + 1.07, zR - 0.43, zR + 0.43, 'sill')
tube(WORLD, OX1 - 0.3, 0.1, OH, OZ1 + 0.08, 0.05, 'sill')

# ===== block on the right (same height as ours) =====
RX0, RX1 = FX1, FX1 + 22.0
Fr = Frame((RX0, 0, 0), (1, 0, 0), (0, 0, 1))
rcols, _ = ribbon(RX1 - RX0, 21, start=0.9)
rrows = [[(a, b, G + f * FL + 0.85, G + f * FL + 0.85 + 1.32) for a, b in rcols] for f in range(2)]
rrows.append([(1.6 + i * 3.4, 3.0 + i * 3.4, 1.0, 2.2) for i in range(6)])
facade(Fr, RX1 - RX0, 0, TOP, rrows, 0.42, 'wall', rng, ends=(False, True))
box(WORLD, RX0, RX1, 0, 0.9, 0, 0.06, 'plinth', ('w0',))
box(WORLD, RX0, RX1, G, TOP, -BD, -0.42, 'wall', ('w0', 'w1', 'u0', 'v0'), {'v1': 'deck'})
box(WORLD, RX0, RX1, 0, G, -BD, -0.42, 'wall', ('w0', 'w1', 'u0', 'v0', 'v1'))
box(WORLD, RX0, RX1 + 0.05, TOP - 0.16, TOP, 0, 0.07, 'wall', ('w0',))
box(WORLD, RX0, RX1, TOP, TOP + 0.45, -0.25, 0.03, 'wall', ('u0',))
for cx, cz in [(34.5, -3.0), (41.0, -3.5), (47.5, -2.8)]:
    box(WORLD, cx - 0.38, cx + 0.38, TOP, TOP + 1.6, cz - 0.38, cz + 0.38, 'wall', ('v0',))
    box(WORLD, cx - 0.46, cx + 0.46, TOP + 1.6, TOP + 1.66, cz - 0.46, cz + 0.46, 'sill')

# ---------- mesh object, plaster UVs (planar by dominant axis, 5.5 m tiles) ----------
me = bpy.data.meshes.new('Building')
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
uvl = bm.loops.layers.uv.new('UVMap')
for f in bm.faces:
    n = f.normal; ax = max(range(3), key=lambda i: abs(n[i]))
    for l in f.loops:
        c = l.vert.co
        l[uvl].uv = ((c.x, c.y) if ax == 2 else (c.y, c.z) if ax == 0 else (c.x, c.z))
        l[uvl].uv = (l[uvl].uv[0] / TILE, l[uvl].uv[1] / TILE)
bm.to_mesh(me); bm.free()
ob = bpy.data.objects.new('Building', me); sc.collection.objects.link(ob)
for n in NAMES:
    m = bpy.data.materials.new(n); m.use_nodes = True
    m.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (*COL[n], 1)
    me.materials.append(m)
me.set_sharp_from_angle(angle=math.radians(30))
print('BUILDING: faces', len(me.polygons), 'verts', len(me.vertices))

# a ground plane so walls darken where they meet the pavement (not exported)
gm = bpy.data.meshes.new('ground'); gb = bmesh.new()
bmesh.ops.create_grid(gb, x_segments=1, y_segments=1, size=120); gb.to_mesh(gm); gb.free()
gnd = bpy.data.objects.new('ground', gm); gnd.location = (7, 10, 0); sc.collection.objects.link(gnd)
gmat = bpy.data.materials.new('ground'); gmat.use_nodes = True; gmat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.42, 0.40, 0.37, 1); gm.materials.append(gmat)

# ---------- bake UVs ----------
bpy.context.view_layer.objects.active = ob; ob.select_set(True)
# only the plastered surfaces get the bake; frames, glass and the rest keep plain materials in the site and park their
# bake UVs on one spare texel so the walls get all the resolution
BAKED = ('wall', 'ochre', 'plinth', 'roof')
lm = me.uv_layers.new(name='Lightmap'); me.uv_layers.active = lm
for p in me.polygons: p.select = NAMES[p.material_index] in BAKED
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.uv.smart_project(angle_limit=math.radians(45), island_margin=0.002, area_weight=0.0, correct_aspect=True, scale_to_bounds=False)
bpy.ops.uv.pack_islands(margin=0.002, rotate=True)
bpy.ops.object.mode_set(mode='OBJECT')
lm = me.uv_layers['Lightmap']          # the edit-mode round trip invalidates the old reference
for p in me.polygons:
    for li in p.loop_indices:
        uv = lm.data[li].uv
        lm.data[li].uv = (uv[0] * 0.992, uv[1] * 0.992) if NAMES[p.material_index] in BAKED else (0.997, 0.997)

# ---------- bake: emission = AO x weathering (streaks, damp blotches, shell marks, grime at the foot of the wall) ----------
img = bpy.data.images.new('AO', SIZE, SIZE, float_buffer=True, alpha=False)
saved = {}
def node(nt, t, **kw):
    n = nt.nodes.new(t)
    for k, v in kw.items(): setattr(n, k, v)
    return n
def sock(socks, name): return next(s for s in socks if s.name == name and s.type == 'RGBA')
def math_(nt, op, a, b=None, clamp=False):
    n = node(nt, 'ShaderNodeMath', operation=op, use_clamp=clamp); L = nt.links
    for i, x in enumerate([a, b]):
        if x is None: continue
        if isinstance(x, (int, float)): n.inputs[i].default_value = x
        else: L.new(x, n.inputs[i])
    return n.outputs[0]
for m in me.materials:
    nt = m.node_tree; L = nt.links
    saved[m.name] = [n.name for n in nt.nodes]
    out = nt.nodes['Material Output']
    ao = node(nt, 'ShaderNodeAmbientOcclusion', samples=16); ao.inputs['Distance'].default_value = 1.2
    aof = math_(nt, 'POWER', ao.outputs['AO'], 0.8)
    if m.name in ('wall', 'ochre'):
        tc = node(nt, 'ShaderNodeTexCoord')
        mp = node(nt, 'ShaderNodeMapping'); mp.inputs['Scale'].default_value = (2.2, 2.2, 0.09); L.new(tc.outputs['Object'], mp.inputs['Vector'])
        st = node(nt, 'ShaderNodeTexNoise'); st.inputs['Scale'].default_value = 1.0; st.inputs['Detail'].default_value = 3; L.new(mp.outputs[0], st.inputs['Vector'])
        streak = math_(nt, 'MULTIPLY', math_(nt, 'SUBTRACT', st.outputs['Fac'], 0.5), 2.2, True)
        bl = node(nt, 'ShaderNodeTexNoise'); bl.inputs['Scale'].default_value = 0.35; bl.inputs['Detail'].default_value = 4; L.new(tc.outputs['Object'], bl.inputs['Vector'])
        blot = math_(nt, 'MULTIPLY', math_(nt, 'SUBTRACT', bl.outputs['Fac'], 0.52), 3.0, True)
        vo = node(nt, 'ShaderNodeTexVoronoi'); vo.inputs['Scale'].default_value = 1.7; L.new(tc.outputs['Object'], vo.inputs['Vector'])
        mark = math_(nt, 'LESS_THAN', vo.outputs['Distance'], 0.045)
        sep = node(nt, 'ShaderNodeSeparateXYZ'); L.new(tc.outputs['Object'], sep.inputs[0])
        foot = math_(nt, 'MULTIPLY', math_(nt, 'SUBTRACT', 1.0, math_(nt, 'DIVIDE', sep.outputs['Z'], 1.3), True), 1.0)
        dirt = math_(nt, 'ADD', math_(nt, 'ADD', math_(nt, 'MULTIPLY', streak, 0.26), math_(nt, 'MULTIPLY', blot, 0.12)),
                     math_(nt, 'ADD', math_(nt, 'MULTIPLY', mark, 0.38), math_(nt, 'MULTIPLY', foot, 0.22)))
        mix = node(nt, 'ShaderNodeMix', data_type='RGBA'); sock(mix.inputs, 'A').default_value = (1, 1, 1, 1); sock(mix.inputs, 'B').default_value = (0.55, 0.47, 0.37, 1)
        L.new(math_(nt, 'MINIMUM', dirt, 1.0), mix.inputs['Factor'])
        mul = node(nt, 'ShaderNodeMix', data_type='RGBA', blend_type='MULTIPLY'); mul.inputs['Factor'].default_value = 1.0
        L.new(sock(mix.outputs, 'Result'), sock(mul.inputs, 'A')); L.new(aof, sock(mul.inputs, 'B')); col = sock(mul.outputs, 'Result')
    else:
        col = aof
    em = node(nt, 'ShaderNodeEmission'); L.new(col, em.inputs['Color']); L.new(em.outputs[0], out.inputs['Surface'])
    tex = node(nt, 'ShaderNodeTexImage', image=img); tex.select = True; nt.nodes.active = tex
sc.render.engine = 'CYCLES'
prefs = bpy.context.preferences.addons['cycles'].preferences
try:
    prefs.compute_device_type = 'METAL'; prefs.refresh_devices()
    for d in prefs.devices: d.use = d.type == 'METAL'
    sc.cycles.device = 'GPU'
except Exception as e:
    print('BUILDING: GPU unavailable', e)
sc.cycles.samples = SAMPLES
bpy.ops.object.select_all(action='DESELECT'); ob.select_set(True); bpy.context.view_layer.objects.active = ob
bpy.ops.object.bake(type='EMIT', margin=4, use_clear=True, target='IMAGE_TEXTURES')
px = np.clip(np.array(img.pixels[:], dtype=np.float32).reshape(SIZE, SIZE, 4)[:, :, :3], 0, 1)
o8 = bpy.data.images.new('AO8', SIZE, SIZE, alpha=False); o8.colorspace_settings.name = 'Non-Color'
o8.pixels[:] = np.concatenate([px, np.ones((SIZE, SIZE, 1), np.float32)], axis=2).ravel()
o8.filepath_raw = os.path.join(OUT, 'building_ao.png'); o8.file_format = 'PNG'; o8.save()
print('BUILDING: baked, mean', float(px.mean()))

# ---------- restore plain materials, export ----------
for m in me.materials:
    nt = m.node_tree
    for n in [n for n in nt.nodes if n.name not in saved[m.name]]: nt.nodes.remove(n)
    nt.links.new(nt.nodes['Principled BSDF'].outputs[0], nt.nodes['Material Output'].inputs['Surface'])
me.uv_layers.active = me.uv_layers[0]
bpy.ops.object.select_all(action='DESELECT'); ob.select_set(True)
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, 'building.glb'), use_selection=True, export_format='GLB',
                          export_texcoords=True, export_normals=True, export_image_format='NONE', export_extras=False,
                          export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=7,
                          export_draco_position_quantization=16, export_draco_normal_quantization=10,
                          export_draco_texcoord_quantization=16)
print('BUILDING: exported')

# ---------- optional: PREVIEW=<dir> renders the square view with sun + sky, AO texture on the diffuse ----------
if os.environ.get('PREVIEW'):
    pv = os.environ['PREVIEW']; os.makedirs(pv, exist_ok=True)
    o8.filepath_raw = os.path.join(OUT, 'building_ao.png')
    for m in me.materials:
        nt = m.node_tree; L = nt.links; bsdf = nt.nodes['Principled BSDF']
        t = node(nt, 'ShaderNodeTexImage', image=o8); uvn = node(nt, 'ShaderNodeUVMap', uv_map='Lightmap'); L.new(uvn.outputs[0], t.inputs[0])
        mul = node(nt, 'ShaderNodeMix', data_type='RGBA', blend_type='MULTIPLY'); mul.inputs['Factor'].default_value = 1.0
        sock(mul.inputs, 'A').default_value = (*COL[m.name], 1); L.new(t.outputs['Color'], sock(mul.inputs, 'B')); L.new(sock(mul.outputs, 'Result'), bsdf.inputs['Base Color'])
        if m.name in ('glass', 'glassLit'): bsdf.inputs['Roughness'].default_value = 0.05
        if m.name in ('roomLit', 'curtainLit'): bsdf.inputs['Emission Color'].default_value = (1, 0.75, 0.45, 1); bsdf.inputs['Emission Strength'].default_value = 0.0
    sun = bpy.data.objects.new('sun', bpy.data.lights.new('sun', 'SUN')); sun.data.energy = 3.5; sc.collection.objects.link(sun)
    sun.rotation_euler = (Vector(tb((6, 0, -4))) - Vector(tb((-25, 44, 40)))).to_track_quat('-Z', 'Y').to_euler()
    wo = bpy.data.worlds.new('sky'); sc.world = wo; wo.use_nodes = True
    bg = wo.node_tree.nodes['Background']; bg.inputs[0].default_value = (0.55, 0.72, 0.92, 1); bg.inputs[1].default_value = 0.9
    cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam; cam.data.lens = 22
    sc.render.resolution_x, sc.render.resolution_y = 1280, 720
    sc.cycles.samples = 96; sc.cycles.use_denoising = True; sc.view_settings.view_transform = 'AgX'
    for name, p, t in [('square', (3, 3.0, 22), (5, 4.4, 0)), ('left', (-12, 2.8, 17), (-8, 6, 0)), ('close', (12, 1.7, 7), (14, 4.0, 0))]:
        cam.location = Vector(tb(p)); cam.rotation_euler = (Vector(tb(t)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = os.path.join(pv, name + '.png'); bpy.ops.render.render(write_still=True)
    print('BUILDING: previews in', pv)

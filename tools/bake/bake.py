# Bakes the flat: blender -b --factory-startup --python tools/bake/bake.py -- <flat_src.glb> <out dir> [lightmap size] [samples]
# Input: the .glb written by tools/bake/export.js (flat-local coords, materials named M<i>, node extras kind/soft).
# Output: flat.glb (bevelled static interior, one mesh, TEXCOORD_1 = lightmap UVs, materials by name only),
#         flat_lm.png (irradiance, sRGB-encoded, divided by `scale`) and flat_lm.json ({"scale": ...}).
import bpy, bmesh, sys, json, math, os
import numpy as np

argv = sys.argv[sys.argv.index('--') + 1:]
SRC, OUT = argv[0], argv[1]
SIZE = int(argv[2]) if len(argv) > 2 else 4096
SAMPLES = int(argv[3]) if len(argv) > 3 else 512
WH = 2.78
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=SRC)
sc = bpy.context.scene
objs = [o for o in sc.objects if o.type == 'MESH']
root = next((o for o in sc.objects if o.type == 'EMPTY' and 'spots' in o.keys()), None)
for o in objs:                       # bake the hierarchy away: every mesh in world (= flat-local) space
    mw = o.matrix_world.copy(); o.parent = None; o.matrix_world = mw
bpy.ops.object.select_all(action='DESELECT')
for o in objs: o.select_set(True)
bpy.context.view_layer.objects.active = objs[0]
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

def kind(o): return o.get('kind', 'solid')
def hexcol(h): return tuple(((int(h[i:i + 2], 16) / 255) ** 2.2) for i in (1, 3, 5))

# ---------- solids: weld, bevel (soft for upholstery), smooth-by-angle ----------
dg = bpy.context.evaluated_depsgraph_get()
solids = [o for o in objs if kind(o) == 'solid']
for o in solids:
    me = o.data
    bm = bmesh.new(); bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bm.to_mesh(me); bm.free()
    if me.has_custom_normals:
        with bpy.context.temp_override(object=o, active_object=o, selected_editable_objects=[o]):
            bpy.ops.mesh.customdata_custom_splitnormals_clear()
    d = sorted(x for x in o.dimensions if x > 1e-4)
    if not d: continue
    mn = d[0]
    soft = o.get('soft', 0)
    w = min(0.04, mn * 0.28) if soft else min(0.007, mn * 0.18)
    if w < 0.0015: continue
    b = o.modifiers.new('bevel', 'BEVEL')
    b.width = w; b.segments = 4 if soft else 2; b.limit_method = 'ANGLE'; b.angle_limit = math.radians(35)
    b.use_clamp_overlap = True; b.profile = 0.5
dg = bpy.context.evaluated_depsgraph_get()
for o in solids:
    if o.modifiers:
        nm = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
        old = o.data; o.modifiers.clear(); o.data = nm; bpy.data.meshes.remove(old)
    for p in o.data.polygons: p.use_smooth = True
    o.data.set_sharp_from_angle(angle=math.radians(32))

# ---------- light carriers ----------
for o in objs:
    k = kind(o)
    if k == 'glass':                  # windows, shower glass: let light through
        o.visible_shadow = False; o.visible_diffuse = False; o.visible_glossy = False; o.visible_transmission = False
    elif k in ('emit', 'screen'):
        col = hexcol(o.get('col', '#ffffff'))
        lum = max(col)
        m = bpy.data.materials.new('emit_' + o.name); m.use_nodes = True
        nt = m.node_tree; nt.nodes.clear()
        out = nt.nodes.new('ShaderNodeOutputMaterial'); em = nt.nodes.new('ShaderNodeEmission')
        em.inputs['Color'].default_value = (*col, 1)
        em.inputs['Strength'].default_value = 1.2 if k == 'screen' else (7.0 if lum > 0.5 else 2.0)
        nt.links.new(em.outputs[0], out.inputs[0])
        o.data.materials.clear(); o.data.materials.append(m)

def to_bl(x, y, z): return (x, -z, y)   # three flat-local -> Blender
warm = (1.0, 0.87, 0.72)   # ~3300 K
if root:
    for sx, sz in [tuple(p) for p in root['spots']]:
        L = bpy.data.lights.new('spot', 'SPOT'); L.energy = 55; L.color = warm
        L.spot_size = math.radians(110); L.spot_blend = 0.7; L.shadow_soft_size = 0.05
        ob = bpy.data.objects.new('spot', L); ob.location = to_bl(sx, WH - 0.12, sz); sc.collection.objects.link(ob)
    lights = root['lights']; lights = eval(lights) if isinstance(lights, str) else [tuple(p) for p in lights]
    for lx, ly, lz, c in lights:     # soft room fill (bounce from shades, ceiling)
        L = bpy.data.lights.new('fill', 'POINT'); L.energy = 45; L.color = warm; L.shadow_soft_size = 0.6
        ob = bpy.data.objects.new('fill', L); ob.location = to_bl(lx, ly, lz); sc.collection.objects.link(ob)

wo = bpy.data.worlds.new('sky'); sc.world = wo; wo.use_nodes = True
bg = wo.node_tree.nodes['Background']; bg.inputs[0].default_value = (0.55, 0.6, 0.68, 1); bg.inputs[1].default_value = 0.55

# ---------- one static mesh with a lightmap UV ----------
bpy.ops.object.select_all(action='DESELECT')
for o in solids: o.select_set(True)
flat = solids[0]; bpy.context.view_layer.objects.active = flat
bpy.ops.object.join()
flat.name = flat.data.name = 'FlatBaked'
me = flat.data
while len(me.uv_layers) > 1: me.uv_layers.remove(me.uv_layers[1])
if not me.uv_layers: me.uv_layers.new(name='UVMap')
lm = me.uv_layers.new(name='Lightmap'); me.uv_layers.active = lm
bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.0025, area_weight=0.0, correct_aspect=True, scale_to_bounds=False)
bpy.ops.uv.pack_islands(margin=0.0025, rotate=True)
bpy.ops.object.mode_set(mode='OBJECT')   # Lightmap stays the active UV: the bake writes through the active layer
print('BAKE: faces', len(me.polygons), 'verts', len(me.vertices), 'materials', len(me.materials))

# ---------- bake irradiance (diffuse direct + indirect, no albedo) ----------
img = bpy.data.images.new('LM', SIZE, SIZE, float_buffer=True, alpha=False)
for m in me.materials:
    if not m: continue
    m.use_nodes = True
    n = m.node_tree.nodes.new('ShaderNodeTexImage'); n.image = img; n.select = True; m.node_tree.nodes.active = n
sc.render.engine = 'CYCLES'
prefs = bpy.context.preferences.addons['cycles'].preferences
try:
    prefs.compute_device_type = 'METAL'; prefs.refresh_devices()
    for d in prefs.devices: d.use = d.type == 'METAL'
    sc.cycles.device = 'GPU'
except Exception as e:
    print('BAKE: GPU unavailable', e)
sc.cycles.samples = SAMPLES; sc.cycles.use_adaptive_sampling = False
sc.cycles.max_bounces = 6; sc.cycles.diffuse_bounces = 4
sc.render.bake.margin = 6; sc.render.bake.use_clear = True
bpy.ops.object.select_all(action='DESELECT'); flat.select_set(True); bpy.context.view_layer.objects.active = flat
bpy.ops.object.bake(type='DIFFUSE', pass_filter={'DIRECT', 'INDIRECT'}, margin=6, use_clear=True, target='IMAGE_TEXTURES')

# ---------- encode: divide by a scale so the bright end fits, sRGB, 8-bit ----------
px = np.array(img.pixels[:], dtype=np.float32).reshape(SIZE, SIZE, 4)[:, :, :3]
lit = px.max(axis=2); p = float(np.percentile(lit[lit > 1e-4], 99.6)) if (lit > 1e-4).any() else 1.0
scale = max(p, 1e-3)
v = np.clip(px / scale, 0, 1)
v = np.where(v <= 0.0031308, v * 12.92, 1.055 * np.power(v, 1 / 2.4) - 0.055)
outimg = bpy.data.images.new('LM8', SIZE, SIZE, alpha=False)
outimg.colorspace_settings.name = 'Non-Color'
outimg.pixels[:] = np.concatenate([v, np.ones((SIZE, SIZE, 1), np.float32)], axis=2).ravel()
outimg.filepath_raw = os.path.join(OUT, 'flat_lm.png'); outimg.file_format = 'PNG'; outimg.save()
json.dump({'scale': scale}, open(os.path.join(OUT, 'flat_lm.json'), 'w'))
print('BAKE: scale', scale)

me.uv_layers.active = me.uv_layers[0]
# ---------- export geometry only (materials keep their M<i> names; textures stay in the site) ----------
for m in me.materials:
    if m:
        for n in [n for n in m.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image == img]: m.node_tree.nodes.remove(n)
bpy.ops.object.select_all(action='DESELECT'); flat.select_set(True)
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, 'flat.glb'), use_selection=True, export_format='GLB',
                          export_texcoords=True, export_normals=True, export_image_format='NONE', export_extras=False,
                          export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=7,
                          export_draco_position_quantization=16, export_draco_normal_quantization=10,
                          export_draco_texcoord_quantization=16)
print('BAKE: done')

# ---------- optional: PREVIEW=<dir> renders a still per room (Cycles, denoised) to judge the light without the site ----------
if os.environ.get('PREVIEW'):
    from mathutils import Vector
    pv = os.environ['PREVIEW']; os.makedirs(pv, exist_ok=True)
    cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
    cam.data.lens = 18
    sc.render.resolution_x, sc.render.resolution_y = 800, 600
    sc.cycles.samples = 128; sc.cycles.use_denoising = True
    sc.view_settings.view_transform = 'AgX'
    views = {'hall': ((-0.15, 1.6, -0.6), (-0.15, 1.2, 2.89)), 'living': ((3.9, 1.6, -0.5), (2.5, 1.0, -3.9)),
             'bedroom': ((-0.6, 1.6, -1.7), (-2.6, 0.9, -3.3)), 'kitchen': ((-3.9, 1.6, -3.6), (-3.9, 1.0, 0.1)),
             'bath': ((-1.0, 1.6, -0.5), (-2.9, 1.0, -0.2))}
    for name, (p, t) in views.items():
        cam.location = Vector(to_bl(*p)); d = Vector(to_bl(*t)) - cam.location
        cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = os.path.join(pv, name + '.png'); bpy.ops.render.render(write_still=True)
    print('BAKE: previews in', pv)

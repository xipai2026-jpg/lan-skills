"""
scene.json → Blender 体块城市 → 渲染出图。必须由 Blender 跑，不是普通 python 脚本：

    /Applications/Blender.app/Contents/MacOS/Blender --background \
        --python build_city.py -- --scene scene.json --outdir renders

`--` 之后的参数才归本脚本，之前的归 Blender。
"""
import bpy, json, math, os, sys
from mathutils import Vector
from mathutils.geometry import tessellate_polygon


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", default="scene.json")
    ap.add_argument("--outdir", default="renders")
    ap.add_argument("--name", default="city", help="出图文件名前缀")
    ap.add_argument("--res", default="1920x1080")
    ap.add_argument("--samples", type=int, default=32)
    ap.add_argument("--tower-height", type=float, default=60,
                    help="超过这个高度的楼单独给玻璃金属材质")
    ap.add_argument("--shots", default="aerial,street",
                    help="出哪几个机位，逗号分隔：aerial / street / top")
    ap.add_argument("--save-blend", default="", help="顺便存一份 .blend 方便手动调")
    return ap.parse_args(argv)


A = parse_args()
BASE = os.path.dirname(os.path.abspath(A.scene)) or "."
DATA = json.load(open(A.scene))

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


def make_mat(name, rgb, rough=0.8, metal=0.0, emit=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*rgb, 1)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if emit > 0:
        bsdf.inputs["Emission Color"].default_value = (*rgb, 1)
        bsdf.inputs["Emission Strength"].default_value = emit
    return m


MAT_BLDG  = make_mat("bldg",  (0.87, 0.85, 0.81), rough=0.9)
MAT_TOWER = make_mat("tower", (0.72, 0.78, 0.84), rough=0.35, metal=0.6)
MAT_ROAD  = make_mat("road",  (0.16, 0.17, 0.19), rough=0.95)
MAT_WATER = make_mat("water", (0.13, 0.35, 0.48), rough=0.1)
MAT_PARK  = make_mat("park",  (0.30, 0.44, 0.24), rough=0.95)
MAT_GND   = make_mat("gnd",   (0.47, 0.45, 0.41), rough=1.0)


def add_object(name, verts, faces, mat):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.validate()
    obj = bpy.data.objects.new(name, mesh)
    obj.data.materials.append(mat)
    scene.collection.objects.link(obj)
    return obj


# ---------- 建筑：全城合并成一个网格，4000+ 栋也是秒级 ----------
def build_buildings(blist, name, mat):
    if not blist:
        return
    verts, faces = [], []
    for b in blist:
        pts, h = b["pts"], b["h"]
        n = len(pts)
        base = len(verts)
        verts += [(x, y, 0.0) for x, y in pts]
        verts += [(x, y, h) for x, y in pts]
        for i in range(n):                       # 侧面
            j = (i + 1) % n
            faces.append((base + i, base + j, base + n + j, base + n + i))
        # 顶面必须三角剖分，L 形/凹多边形直接连成一个面会破洞
        for t in tessellate_polygon(([Vector((x, y, 0)) for x, y in pts],)):
            faces.append(tuple(base + n + i for i in t))
    add_object(name, verts, faces, mat)


TH = A.tower_height
build_buildings([b for b in DATA["buildings"] if b["h"] < TH], "city_low", MAT_BLDG)
build_buildings([b for b in DATA["buildings"] if b["h"] >= TH], "city_high", MAT_TOWER)


# ---------- 折线 → 有宽度的条带 ----------
def strip_from_line(pts, w, z):
    verts, faces = [], []
    hw = w / 2
    for i in range(len(pts) - 1):
        (x1, y1), (x2, y2) = pts[i], pts[i + 1]
        dx, dy = x2 - x1, y2 - y1
        L = math.hypot(dx, dy)
        if L < 0.01:
            continue
        ox, oy = -dy / L * hw, dx / L * hw
        base = len(verts)
        verts += [(x1 + ox, y1 + oy, z), (x1 - ox, y1 - oy, z),
                  (x2 - ox, y2 - oy, z), (x2 + ox, y2 + oy, z)]
        faces.append((base, base + 1, base + 2, base + 3))
    return verts, faces


def build_strips(items, name, mat, z, default_w=10):
    V, F = [], []
    for it in items:
        v, f = strip_from_line(it["pts"], it.get("w", default_w), z)
        off = len(V)
        V += v
        F += [tuple(off + i for i in face) for face in f]
    if V:
        add_object(name, V, F, mat)


def build_polys(items, name, mat, z):
    V, F = [], []
    for it in items:
        pts = it["pts"]
        base = len(V)
        V += [(x, y, z) for x, y in pts]
        for t in tessellate_polygon(([Vector((x, y, 0)) for x, y in pts],)):
            F += [tuple(base + i for i in t)]
    if V:
        add_object(name, V, F, mat)


build_strips(DATA.get("roads", []), "roads", MAT_ROAD, 0.15)
build_strips([w for w in DATA.get("waters", []) if w.get("line")], "rivers", MAT_WATER, 0.08, 30)
build_polys([w for w in DATA.get("waters", []) if not w.get("line")], "lakes", MAT_WATER, 0.08)
build_polys(DATA.get("parks", []), "parks", MAT_PARK, 0.04)


# ---------- 按数据范围自动定地面与机位（换城市不用改代码） ----------
xs, ys, hs = [], [], [1.0]
for key in ("buildings", "roads", "waters", "parks"):
    for it in DATA.get(key, []):
        for x, y in it["pts"]:
            xs.append(x); ys.append(y)
        if "h" in it:
            hs.append(it["h"])
if not xs:
    raise SystemExit("scene.json 里没有任何几何")
cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
R = max(max(xs) - min(xs), max(ys) - min(ys)) / 2 or 500.0
HMAX = max(hs)
G = R * 1.55
add_object("ground",
           [(cx - G, cy - G, 0), (cx + G, cy - G, 0), (cx + G, cy + G, 0), (cx - G, cy + G, 0)],
           [(0, 1, 2, 3)], MAT_GND)

sun = bpy.data.lights.new("sun", "SUN")
sun.energy = 6.5
sun.angle = math.radians(1.0)
sun.color = (1.0, 0.93, 0.82)
sun_o = bpy.data.objects.new("sun", sun)
sun_o.rotation_euler = (math.radians(63), 0, math.radians(-40))   # 25° 仰角出长影
scene.collection.objects.link(sun_o)

world = bpy.data.worlds.new("w")
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs[0].default_value = (0.55, 0.65, 0.80, 1)
bg.inputs[1].default_value = 0.45
scene.world = world

rx, ry = [int(v) for v in A.res.lower().split("x")]
scene.render.engine = "BLENDER_EEVEE_NEXT"
scene.eevee.use_gtao = True
scene.eevee.use_raytracing = True
scene.eevee.gtao_distance = 60
scene.eevee.taa_render_samples = A.samples
scene.render.resolution_x = rx
scene.render.resolution_y = ry
scene.view_settings.look = "AgX - Punchy"
scene.view_settings.exposure = 0.35

cam = bpy.data.cameras.new("cam")
cam.lens = 40
cam.clip_start = 1.0
cam.clip_end = max(30000, R * 20)   # ⚠️ 默认 100m，城市尺度必须放大，否则整城被裁只剩天空
cam_o = bpy.data.objects.new("cam", cam)
scene.collection.objects.link(cam_o)
scene.camera = cam_o


def aim(pos, target):
    cam_o.location = pos
    d = Vector(target) - Vector(pos)
    cam_o.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


SHOTS = {
    "aerial": ((cx - 0.68 * R, cy - 0.79 * R, 0.42 * R), (cx, cy, HMAX * 0.3)),
    "street": ((cx - 0.29 * R, cy - 0.53 * R, 0.15 * R), (cx, cy + 0.1 * R, HMAX * 0.5)),
    "top":    ((cx, cy, R * 1.6), (cx, cy, 0)),
}

outdir = A.outdir if os.path.isabs(A.outdir) else os.path.join(BASE, A.outdir)
os.makedirs(outdir, exist_ok=True)
made = []
for shot in [s.strip() for s in A.shots.split(",") if s.strip()]:
    if shot not in SHOTS:
        print("跳过未知机位 %s（可选 %s）" % (shot, "/".join(SHOTS)))
        continue
    aim(*SHOTS[shot])
    path = os.path.join(outdir, "%s_%s.png" % (A.name, shot))
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    made.append(path)

if A.save_blend:
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(A.save_blend))

print("CITY_DONE buildings=%d objects=%d span=%.0fm hmax=%.0fm shots=%s"
      % (len(DATA["buildings"]), len(scene.collection.objects), R * 2, HMAX, ",".join(made)))

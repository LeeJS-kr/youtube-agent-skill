"""신정동 롱폼 3D 재구성 컷 (흰 클레이 + 포인트 색). Blender 4.5+/bpy 5.x, 헤드리스.
  blender -b -P sinjeong3d.py -- --scene op_alley --out DIR [--res 1920x1080] [--samples 64] [--gpu] [--still F ...] [--engine CYCLES]
결과: DIR/<scene>/####.png (프레임) -> ffmpeg 로 mp4.
실제 건물·장소와 다르게 일반화한 모형. 사람은 얼굴 없는 마네킹, 시신 없음.
"""
import sys, os, math, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
import claykit as ck

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
ap = argparse.ArgumentParser()
ap.add_argument("--scene", required=True)
ap.add_argument("--out", default="/tmp/sj3d")
ap.add_argument("--res", default="1920x1080")
ap.add_argument("--samples", type=int, default=64)
ap.add_argument("--engine", default="CYCLES")
ap.add_argument("--gpu", action="store_true")
ap.add_argument("--still", type=int, nargs="*")
a = ap.parse_args(argv)
W, H = map(int, a.res.split("x"))

YELLOW = (0.78, 0.62, 0.30, 1)    # 누런 포대
BLUE = (0.25, 0.48, 0.85, 1)      # 병원 층 / 역
WARM = (1.0, 0.72, 0.38, 1)
PURPLE = (0.45, 0.22, 0.62, 1)   # 지하철 5호선 색 (신정역)
RED = ck.ACCENT


def setup(frames, night=False):
    s = ck.reset((W, H), a.samples, a.engine)
    s.frame_start, s.frame_end = 1, frames
    if a.gpu and a.engine == "CYCLES":
        pr = bpy.context.preferences.addons["cycles"].preferences
        for t in ("OPTIX", "CUDA"):
            try:
                pr.compute_device_type = t
                (pr.refresh_devices if hasattr(pr, "refresh_devices") else pr.get_devices)()
                if any(d.type == t for d in pr.devices):
                    for d in pr.devices: d.use = d.type == t
                    break
            except Exception as e: print("gpu setup", t, e)
        s.cycles.device = "GPU"
        print("CYCLES DEVICES:", pr.compute_device_type, [(d.name, d.type, d.use) for d in pr.devices], flush=True)
        try: s.cycles.denoiser = "OPTIX"
        except Exception: pass
    if a.engine == "CYCLES":
        s.cycles.max_bounces = 5
        s.cycles.use_denoising = True
        s.cycles.use_adaptive_sampling = True; s.cycles.adaptive_threshold = 0.03
        s.cycles.use_light_tree = True
    s.render.film_transparent = False
    if night:
        nt = s.world.node_tree
        bgs = [n for n in nt.nodes if n.type == "BACKGROUND"]
        bgs[0].inputs[0].default_value = (0.35, 0.42, 0.62, 1); bgs[0].inputs[1].default_value = 0.10
        bgs[1].inputs[0].default_value = (0.05, 0.065, 0.10, 1); bgs[1].inputs[1].default_value = 1.0
        sun = bpy.data.objects["sun"]; sun.data.energy = 0.35; sun.data.color = (0.6, 0.7, 1.0)
        s.view_settings.exposure = 0.2
    return s


def plight(loc, energy, color=(1, 0.8, 0.55), r=0.2, name="pl"):
    L = bpy.data.lights.new(name, "POINT"); L.energy = energy; L.color = color; L.shadow_soft_size = r
    o = bpy.data.objects.new(name, L); o.location = loc; bpy.context.scene.collection.objects.link(o); return o


def area(loc, rot, energy, size=4, color=(1, 1, 1), name="ar"):
    L = bpy.data.lights.new(name, "AREA"); L.energy = energy; L.size = size; L.color = color
    o = bpy.data.objects.new(name, L); o.location = loc; o.rotation_euler = rot; bpy.context.scene.collection.objects.link(o); return o


def key(obj, path, frames_vals, idx=None):
    for f, v in frames_vals:
        if idx is None: setattr(obj, path, v)
        else: getattr(obj, path)[idx] = v
        obj.keyframe_insert(path, frame=f, index=-1 if idx is None else idx)


def lamp_post(x, y, h=4.2, energy=180):
    ck.cyl((x, y, h / 2), 0.07, h)
    ck.box((x + 0.35, y, h), (0.8, 0.18, 0.1), bevel=0.02)
    ck.sphere((x + 0.65, y, h - 0.1), 0.12, m=ck.mat("bulb", WARM, emit=8))
    return plight((x + 0.65, y, h - 0.35), energy, r=0.25)


def sack(loc, rot=0, ln=1.5):
    o = ck.sphere(loc, 0.5, m=ck.mat("sack", YELLOW, rough=0.85), scale=(ln / 1.0, 0.62, 0.42))
    o.rotation_euler = (0, 0, rot)
    for t in (-0.3, 0.3):  # 노끈 두 줄: 포대 표면을 감는 얇은 고리 (2026-11-28: 원판처럼 잘라 보이던 문제 수정)
        cx, cy = loc[0] + t * ln * math.cos(rot), loc[1] + t * ln * math.sin(rot)
        bpy.ops.mesh.primitive_torus_add(major_radius=1.0, minor_radius=0.03, location=(cx, cy, loc[2]), rotation=(0, math.pi / 2, rot))
        r = bpy.context.object
        r.rotation_euler = (0, math.pi / 2, rot)
        r.scale = (0.165, 0.25, 1.0)  # 링 반지름 = 포대 단면(높이 0.21, 폭 0.31)
        r.data.materials.append(ck.mat("twine", (0.45, 0.4, 0.32, 1)))
    return o


def villa(x, y, w, d, floors, h=3.0, lit=()):
    ck.box((x, y, floors * h / 2), (w, d, floors * h), bevel=0.08)
    for f in range(floors):
        for i in range(max(1, int(w / 3))):
            wx = x - w / 2 + (i + 0.5) * w / max(1, int(w / 3))
            on = (f, i) in lit
            ck.box((wx, y - d / 2 - 0.02, f * h + 1.6), (1.3, 0.06, 1.1),
                   m=ck.mat("win_on" if on else "win", WARM if on else (0.3, 0.32, 0.36, 1), emit=6 if on else 0), bevel=0)


def cam_path(cam, tgt, keys_cam, keys_tgt):
    ck.key_smooth(cam, keys_cam); ck.key_smooth(tgt, keys_tgt)


# ======================================================================= scenes
def op_alley():
    """밤 골목, 담벼락 아래 누런 포대 두 개(형태만), 천천히 다가감. 7초"""
    s = setup(210, night=True)
    ck.ground()
    ck.box((0, 0, 0.02), (60, 4.2, 0.04), ck.GROUND, bevel=0)          # 골목 바닥
    for side in (-1, 1):
        for i, x in enumerate(range(-24, 26, 8)):
            hh = (2.2, 2.6, 2.0, 2.4)[i % 4]
            ck.box((x, side * 2.35, hh / 2), (7.8, 0.4, hh), bevel=0.05)  # 담
            villa(x, side * 7.5, 7, 9, 3 if i % 2 else 2, lit={(1, 1)} if (i + side) % 3 == 0 else ())
    lamp_post(3.5, 1.7, energy=260)
    lamp_post(-14, -1.7, energy=120)
    for x, y in ((-1.2, 1.55), (-2.4, 1.6), (0.6, 1.62)):   # 쓰레기 봉투 (흰 클레이)
        ck.sphere((x, y, 0.26), 0.3, scale=(1, 0.9, 0.85))
    sack((-1.0, 1.0, 0.2), 0.55, 1.7)
    sack((0.9, 0.95, 0.2), 0.35, 1.5)
    cam, tgt = ck.camera(lens=35)
    cam_path(cam, tgt, [(1, (-14, -0.6, 1.6)), (210, (-5.5, -0.3, 1.25))], [(1, (0, 0.9, 0.4)), (210, (-0.2, 1.1, 0.25))])
    return s


def op_route():
    """신정역 출구 -> 사거리 -> 상가 빌딩. 빨간 선이 그려지고 작은 사람이 걸어감. 6초"""
    s = setup(180)
    ck.ground()
    ck.road(-40, 40, -4, 4); r2 = ck.box((0, 0, 0.012), (8, 80, 0.045), ck.GROUND, bevel=0)
    for yy in list(range(-38, -5, 4)) + list(range(6, 39, 4)): ck.box((0, yy, 0.04), (0.16, 1.6, 0.02), bevel=0)
    for i in range(6): ck.box((-5.2 + i * 0.0, -3 + i * 1.2, 0.045), (1.6, 0.6, 0.02), bevel=0)  # 횡단보도
    ck.box((-14, -7.5, 1.3), (4.0, 2.8, 0.3), m=ck.mat("stn", PURPLE, rough=0.4, emit=0.4), bevel=0.1)   # 역 출구 지붕
    for dx in (-1.8, 1.8): ck.box((-14 + dx, -7.5, 0.6), (0.2, 2.6, 1.2), m=ck.mat("stn", PURPLE, rough=0.4, emit=0.4), bevel=0.05)
    ck.box((-14, -7.5, 0.05), (2.6, 1.8, 0.1), ck.GROUND, bevel=0)
    for x, y, w, d, h in [(-30, -18, 10, 8, 6), (-26, 12, 12, 10, 14), (-12, 13, 10, 9, 8), (16, -14, 12, 12, 11), (30, -13, 10, 10, 7)]:
        ck.building(x, y, w, d, h)
    ck.building(13, 12, 11, 10, 16)                                    # 그 빌딩
    ck.box((13, 12 - 5.05, 6.6), (11.2, 0.12, 2.6), m=ck.mat("clinic", BLUE, emit=0.6), bevel=0.02)  # 병원 층 (파랑, 단면 장면과 같은 색)
    for x in (-30, -22, 22, 32):
        ck.tree(x, 5.6, 0.8); ck.tree(x, -5.6, 0.8)
    pts = [(-14, -6.2), (-8, -5.2), (-5, -5.2), (-5, 5.2), (8.5, 5.2), (11, 6.8)]
    ck.trail("route", pts, grow=(20, 150))
    fig = ck.figure("w", 2.2, color=ck.ACCENT)
    ck.walk(fig, [(20, pts[0]), (55, pts[1]), (68, pts[2]), (105, pts[3]), (140, pts[4]), (150, pts[5])], 1, 180)
    cam, tgt = ck.camera(lens=30)
    cam_path(cam, tgt, [(1, (-10, -46, 34)), (180, (-4, -38, 27))], [(1, (-2, 1, 0)), (180, (1, 3, 1))])
    return s


def op_window():
    """그 빌딩, 밤. 창문 하나만 켜져 있고 카메라가 천천히 올라감. 7초"""
    s = setup(210, night=True)
    ck.ground(); ck.road(-40, 40, -10, -2)
    villa(0, 4, 14, 10, 5, h=3.2, lit={(1, 2)})
    villa(-15, 5, 10, 9, 3); villa(14, 5, 10, 9, 4)
    ck.box((0, -1.3, 0.08), (60, 1.6, 0.16), bevel=0.03)
    lamp_post(-5, -1.0, energy=150); lamp_post(8, -1.0, energy=150)
    cam, tgt = ck.camera(lens=40)
    cam_path(cam, tgt, [(1, (2, -26, 2.2)), (210, (1, -22, 6.5))], [(1, (0, 0, 4)), (210, (1.5, 0, 5.2))])
    return s


def map3d():
    """위에서 본 동네 블록. 역(파랑) + 두 발견 지점(빨간 핀) 이 빨간 선으로 이어짐. 7초"""
    s = setup(210)
    ck.ground()
    import random; rnd = random.Random(4)
    for gx in range(-5, 6):
        for gy in range(-4, 5):
            x, y = gx * 9, gy * 9
            if abs(gx) <= 0 and abs(gy) <= 0: continue
            ck.box((x, y, 0.4 + rnd.random() * 0.8), (7.2, 7.2, 0.8 + rnd.random() * 1.6), bevel=0.15)
    ck.cyl((0, 0, 0.6), 3.0, 1.2, m=ck.mat("stn", PURPLE, rough=0.4, emit=0.3))
    pins = [(-22.5, 13.5), (18, -22.5)]
    for i, (x, y) in enumerate(pins):
        p = ck.empty(f"pin{i}", (x, y, 0))
        ck.cyl((0, 0, 2.4), 0.22, 4.8, m=ck.mat("pinm", RED, emit=0.4), parent=p)
        ck.sphere((0, 0, 5.2), 1.3, m=ck.mat("pinm", RED, emit=0.4), parent=p)
        f0 = 30 + i * 40
        key(p, "location", [(f0, (x, y, 14)), (f0 + 14, (x, y, 0))])
        route = [(0, 0), (0, 4.5), (-22.5, 4.5), (x, y)] if i == 0 else [(0, 0), (4.5, 0), (4.5, -22.5), (x, y)]
        ck.trail(f"ln{i}", route, width=0.35, z=0.3, grow=(f0 + 30, f0 + 80))  # 골목(블록 사이)으로만 지나감
    cam, tgt = ck.camera(lens=32)
    cam_path(cam, tgt, [(1, (0, -60, 70)), (210, (6, -48, 58))], [(1, (0, 0, 0)), (210, (-2, -2, 0))])
    return s


SOIL = (0.42, 0.40, 0.38, 1)


def soil_around(x0, x1, y0, y1, depth, extent=40):
    """건물 자리(x0..x1, y0..y1)만 비운 땅. 앞(y<y0)은 잘라낸 단면이라 비어 있음."""
    m = ck.mat("soil", SOIL, rough=0.9)
    ck.box(((x0 - extent + x0) / 2, (y0 + y1 + extent) / 2, -depth / 2), (extent, y1 - y0 + extent, depth), m=m, bevel=0)
    ck.box(((x1 + x1 + extent) / 2, (y0 + y1 + extent) / 2, -depth / 2), (extent, y1 - y0 + extent, depth), m=m, bevel=0)
    ck.box(((x0 + x1) / 2, (y1 + y1 + extent) / 2, -depth / 2), (x1 - x0, extent, depth), m=m, bevel=0)
    top = ck.mat("topsoil", ck.WHITE)
    for xc, w in (((x0 - extent + x0) / 2, extent), ((x1 + x1 + extent) / 2, extent)):
        ck.box((xc, (y0 + y1 + extent) / 2, 0.02), (w, y1 - y0 + extent, 0.04), m=top, bevel=0)
    ck.box(((x0 + x1) / 2, (y1 + y1 + extent) / 2, 0.02), (x1 - x0, extent, 0.04), m=top, bevel=0)
    # 멀리 보이는 바닥 (카메라 아래쪽 빈 공간 메우기)
    ck.box((0, y0 - 60, -depth - 0.1), (200, 120, 0.2), m=ck.mat("far", (0.75, 0.75, 0.74, 1)), bevel=0)


def _villa_section(lit=True):
    """다세대 주택 단면 (앞면 없음): 반지하 방(-1.6~1.3) + 1층 현관. 왼쪽에 반지하 문 -> 바깥 계단."""
    soil_around(-8.2, 8.2, -5, 5.2, 4.0)
    ck.box((0, 0, -1.7), (16, 10, 0.2), bevel=0)                      # 반지하 바닥
    ck.box((0, 5, 0.6), (16, 0.3, 4.8), bevel=0.03)                   # 뒷벽
    ck.box((-8, 0, 0.6), (0.3, 10, 4.8), bevel=0.03); ck.box((8, 0, 0.6), (0.3, 10, 4.8), bevel=0.03)
    ck.box((0, 0, 1.3), (16, 10, 0.25), bevel=0.02)                   # 1층 바닥
    ck.box((0, 0, 3.1), (16, 10, 0.2), bevel=0.02)                    # 1층 천장
    ck.box((-1.5, 0.5, -0.2), (0.25, 9, 2.9), bevel=0.02)             # 반지하 방 / 계단실 벽
    ck.box((-5.0, 5.0 - 0.2, 0.6), (1.4, 0.2, 0.2), m=ck.mat("winl", (0.95, 0.9, 0.75, 1), emit=2.5), bevel=0)  # 높은 창 (빛)
    # 반지하 안쪽 계단: 반지하 바닥(-1.6) -> 1층 바닥(1.4), 계단실 x=-0.2..1.4
    for i in range(10):
        ck.box((0.6, -3.5 + i * 0.6, -1.45 + i * 0.3), (1.6, 0.6, 0.3), bevel=0.02)
    # 방 바닥의 노끈 뭉치 (빨강 포인트)
    for x, y in ((-6.0, 2.0), (-4.6, 3.0), (-6.6, 3.6)):
        t = ck.cyl((x, y, -1.53), 0.32, 0.1, m=ck.mat("twine_r", RED, emit=0.3))
    # 1층 현관: 신발장 + 현관문
    cab = ck.empty("cab", (5.0, 4.3, 1.42))
    ck.box((0, 0, 0.95), (2.6, 0.75, 1.9), bevel=0.04, parent=cab)                      # 몸통
    for dx in (-0.65, 0.65):
        ck.box((dx, -0.39, 0.95), (1.24, 0.04, 1.8), m=ck.mat("door", (0.88, 0.88, 0.86, 1)), bevel=0.01, parent=cab)
        ck.box((dx + (-0.48 if dx > 0 else 0.48), -0.43, 1.0), (0.05, 0.04, 0.3), m=ck.mat("hnd", (0.35, 0.35, 0.36, 1), rough=0.3), bevel=0.005, parent=cab)
    for dx in (-1.0, 1.0):
        ck.box((dx, 0, 0.03), (0.12, 0.6, 0.06), bevel=0.0, parent=cab)
    mark = ck.box((5.65, 3.90, 2.95), (0.36, 0.03, 0.36), m=ck.mat("mark", (1, 1, 1, 1), emit=1.2 if lit else 0), bevel=0.01)
    ck.box((7.85, 2.5, 2.2), (0.08, 1.8, 1.7), m=ck.mat("fdoor", (0.6, 0.6, 0.62, 1), rough=0.35), bevel=0.02)       # 현관문
    for i, x in enumerate((3.6, 4.3, 6.9)):  # 신발
        ck.box((x, 3.5 - 0.2 * i, 1.5), (0.45, 0.22, 0.16), bevel=0.06)
        ck.box((x + 0.05, 3.25 - 0.2 * i, 1.5), (0.45, 0.22, 0.16), bevel=0.06)
    return cab, mark


def banjiha_stairs():
    """반지하 방에서 사람이 뛰쳐나와 안쪽 계단으로 1층까지 올라감. 7초"""
    s = setup(210)
    _villa_section()
    fig = ck.figure("v", 1.6, color=(0.95, 0.95, 0.95, 1))
    pts = [(-6.0, 0.5), (-3.0, -2.5), (0.6, -4.0), (0.6, -3.5), (0.6, 2.4), (2.4, 1.0)]
    ck.walk(fig, [(25, pts[0]), (60, pts[1]), (85, pts[2]), (92, pts[3]), (170, pts[4]), (195, pts[5])], 1, 210, run=True)
    zk = [(1, -1.6), (92, -1.6), (170, 1.43), (210, 1.43)]
    for f in range(1, 211):
        z = ck._interp([(fr, (v, 0)) for fr, v in zk], f).x
        fig["root"].location.z = z; fig["root"].keyframe_insert("location", index=2, frame=f)
    cam, tgt = ck.camera(lens=30)
    cam_path(cam, tgt, [(1, (-5, -13, 1.2)), (100, (-1.5, -12, 1.4)), (210, (1.5, -11.5, 3.2))],
             [(1, (-4.5, 0, -1.0)), (100, (0.3, -1, -0.6)), (210, (1.2, 1, 1.4))])  # 사람을 따라가며 가까이
    return s


def shoe_cabinet(off=False):
    """1층 현관 신발장, 스티커 자리만 흰 자국. off=True: 불이 꺼짐. 7초 / 10초"""
    n = 300 if off else 210
    s = setup(n)
    cab, mark = _villa_section(lit=True)
    bulb = plight((5.0, 1.8, 2.9), 120, color=(1, 0.85, 0.65), r=0.3, name="hall")
    if off:
        key(bulb.data, "energy", [(1, 120), (150, 120), (190, 0)])
        mm = mark.data.materials[0].node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
        mm.default_value = 1.2; mm.keyframe_insert("default_value", frame=150); mm.default_value = 0.0; mm.keyframe_insert("default_value", frame=195)
        w = bpy.context.scene.world.node_tree.nodes["Background"].inputs[1]
        w.default_value = 0.35; w.keyframe_insert("default_value", frame=150); w.default_value = 0.03; w.keyframe_insert("default_value", frame=200)
        sun = bpy.data.objects["sun"].data; key(sun, "energy", [(150, 5.0), (200, 0.2)])
    cam, tgt = ck.camera(lens=40)
    cam_path(cam, tgt, [(1, (1.8, -6.5, 2.7)), (n, (3.8, -2.4, 2.8))], [(1, (5.0, 4.0, 2.3)), (n, (5.5, 3.9, 2.8))])
    return s


def _building_section(floors=5):
    """상가 빌딩 단면: 지하 2층 + 지상 5층, 앞면 없음. 왼쪽에 인도. 반환: 층 바닥 높이 dict"""
    h = 3.2; zs = {}
    soil_around(-7.2, 7.2, -5, 5.2, 2 * h + 0.6)
    for lvl in range(-2, floors):
        z = lvl * h; zs[lvl] = z
        ck.box((0, 0, z - 0.12), (14, 10, 0.24), bevel=0.02)
        for i in (-1, 1):  # 칸막이
            ck.box((i * 3.0, 2.5, z + h / 2), (0.15, 5, h - 0.3), bevel=0.01)
    tot = floors * h + 2 * h; zc = (floors * h - 2 * h) / 2
    ck.box((0, 5, zc), (14, 0.3, tot), bevel=0.02)
    ck.box((-7, 0, zc), (0.3, 10, tot), bevel=0.02); ck.box((7, 0, zc), (0.3, 10, tot), bevel=0.02)
    ck.box((0, 0, floors * h), (14.4, 10.4, 0.4), bevel=0.04)
    for lvl in range(-2, floors):  # 계단실 (오른쪽 뒤) 표시: 층마다 작은 계단
        for i in range(6):
            ck.box((5.3, 1.0 + i * 0.5, lvl * h + 0.27 * i + 0.1), (1.2, 0.5, 0.27), bevel=0.01)
    for x, w_, d_, hh in ((-24, 12, 10, 14), (22, 12, 10, 10), (-40, 10, 10, 8), (36, 10, 10, 18)):  # 이웃 건물
        ck.building(x, 6 + d_ / 2, w_, d_, hh)
    return zs, h


def section(clinic=False):
    """빌딩 단면. clinic=False: 맨 아래 B2가 빨갛게 -> 위 병원 층(2층)이 파랗게. 10초
       clinic=True: 사람이 인도를 걸어와 건물로 들어가고, 파란 선이 병원 층으로. 7초"""
    n = 210 if clinic else 300
    s = setup(n)
    zs, h = _building_section()
    b2 = ck.box((0, 0, zs[-2] + 1.45), (13.4, 9.4, 2.7), m=ck.mat("b2", RED, emit=0.35), bevel=0.05)
    cl = ck.box((0, 0, zs[2] + 0.06), (13.4, 9.4, 0.1), m=ck.mat("clinic", BLUE, emit=0.0), bevel=0.02)
    clm = cl.data.materials[0].node_tree.nodes["Principled BSDF"]
    if not clinic:
        b2.scale = (1, 1, 0.02); b2.keyframe_insert("scale", frame=40); b2.scale = (1, 1, 1); b2.keyframe_insert("scale", frame=95)
        cl.scale = (1, 1, 0.02); cl.keyframe_insert("scale", frame=170); cl.scale = (1, 1, 1); cl.keyframe_insert("scale", frame=200)
        e = clm.inputs["Emission Strength"]; e.default_value = 0; e.keyframe_insert("default_value", frame=170); e.default_value = 1.5; e.keyframe_insert("default_value", frame=215)
        cam, tgt = ck.camera(lens=28)
        cam_path(cam, tgt, [(1, (-16, -40, 4)), (n, (8, -38, 7))], [(1, (0, 0, 1.5)), (n, (0, 0, 2.5))])
    else:
        clm.inputs["Emission Strength"].default_value = 1.5
        b2.hide_render = True
        fig = ck.figure("v", 1.6, color=(0.95, 0.95, 0.95, 1))
        pts = [(-26, -3.6), (-9, -3.6), (-6.2, -3.6), (-3.5, -2.0)]
        ck.walk(fig, [(10, pts[0]), (85, pts[1]), (100, pts[2]), (115, pts[3])], 1, 130)
        ck.visible(fig["root"], [(1, True), (120, False)])
        ck.trail("in", pts, color=BLUE, width=0.1, z=0.08, grow=(10, 118))
        col = ck.cyl((-3.5, -2.0, zs[2] / 2), 0.18, zs[2], m=ck.mat("lift", BLUE, emit=1.2))
        col.scale = (1, 1, 0.01); col.keyframe_insert("scale", frame=118); col.scale = (1, 1, 1); col.keyframe_insert("scale", frame=160)
        cam, tgt = ck.camera(lens=30)
        cam_path(cam, tgt, [(1, (-22, -30, 5)), (n, (-6, -26, 9))], [(1, (-8, -2, 2)), (n, (-1, 0, 6.5))])
    return s


def b2_stairs():
    """1층에서 지하 2층으로 내려가는 계단, 아래쪽에 빨간 빛. 카메라가 따라 내려감. 사람 없음. 7초"""
    s = setup(210, night=True)
    wm = ck.mat("wall", (0.78, 0.78, 0.76, 1))
    ck.box((0, -3, -0.1), (2.4, 6, 0.2), bevel=0)                    # 1층 바닥 (계단 위)
    for i in range(26):
        ck.box((0, i * 0.3 + 0.15, -i * 0.24 - 0.12), (2.0, 0.3, 0.24), bevel=0.012)
    for sx in (-1.15, 1.15):
        ck.box((sx, 3.5, -2.5), (0.3, 13, 7.0), m=wm, bevel=0.02)
    ck.box((0, 9.0, -6.3), (2.4, 2.4, 0.2), bevel=0)                 # B2 층계참
    ck.box((0, 10.3, -4.0), (2.4, 0.2, 5.0), m=wm, bevel=0)
    ck.box((0.0, 10.18, -5.25), (1.0, 0.05, 2.0), m=ck.mat("b2door", (0.25, 0.25, 0.27, 1), rough=0.3), bevel=0.01)
    plight((0, 9.0, -4.8), 130, color=(1.0, 0.1, 0.06), r=0.5, name="red")
    plight((0, -2.0, 2.2), 60, color=(0.85, 0.9, 1.0), r=0.2, name="top")
    cam, tgt = ck.camera(lens=26)
    cam_path(cam, tgt, [(1, (0.2, -3.2, 2.4)), (210, (0.15, 2.2, -0.4))], [(1, (0, 6, -3.6)), (210, (0, 9.6, -5.4))])
    return s


SCENES = dict(op_alley=op_alley, op_route=op_route, op_window=op_window, map=map3d, banjiha_stairs=banjiha_stairs,
              shoe_cabinet=lambda: shoe_cabinet(False), shoe_off=lambda: shoe_cabinet(True),
              section=lambda: section(False), section_clinic=lambda: section(True), b2_stairs=b2_stairs)

s = SCENES[a.scene]()
od = os.path.join(a.out, a.scene); os.makedirs(od, exist_ok=True)
s.render.image_settings.file_format = "PNG"
if a.still is not None:
    for f in (a.still or [s.frame_end // 2]):
        s.frame_set(f); s.render.filepath = os.path.join(od, f"still_{f:04d}.png")
        bpy.ops.render.render(write_still=True)
else:
    s.render.filepath = os.path.join(od, "")
    bpy.ops.render.render(animation=True)
print("DONE", a.scene, od)

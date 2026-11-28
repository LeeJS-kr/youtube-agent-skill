"""claykit: reusable white-clay 3D reconstruction kit for Misstery Files (Blender 5.x bpy, headless).

All-white clay world, color only on key points (ACCENT red, or a case-specific accent such as a black car).
Faceless mannequin figures only. Import from a scene script:  import claykit as ck
"""
import bpy, math
from mathutils import Vector

FPS = 30
WHITE = (0.82, 0.82, 0.80, 1)
GROUND = (0.55, 0.55, 0.55, 1)   # roads a touch darker than buildings
ACCENT = (0.80, 0.02, 0.02, 1)  # red: danger moment / key object
BLACK = (0.025, 0.025, 0.03, 1)

_mats = {}


def reset(res=(720, 1280), samples=16, engine="CYCLES"):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    s = bpy.context.scene
    s.render.fps = FPS
    s.render.resolution_x, s.render.resolution_y = res
    s.render.engine = engine
    if engine == "CYCLES":
        s.cycles.device = "CPU"
        s.cycles.samples = samples
        s.cycles.use_denoising = True
        s.cycles.max_bounces = 4
        s.render.use_persistent_data = True
    if engine == "BLENDER_WORKBENCH":  # fast preview / draft clay look
        sh = s.display.shading
        sh.light = "STUDIO"
        sh.color_type = "MATERIAL"
        sh.show_shadows = True
        sh.shadow_intensity = 0.35
        sh.show_cavity = True
        sh.cavity_type = "BOTH"
        s.display.render_aa = "16"
        s.display.shading.use_dof = False
    s.view_settings.view_transform = "AgX"
    s.view_settings.look = "AgX - Medium High Contrast"
    s.view_settings.exposure = -0.45
    w = bpy.data.worlds.new("w")
    s.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes["Background"]
    bg.inputs[0].default_value = (0.90, 0.92, 0.96, 1)
    bg.inputs[1].default_value = 0.35          # light that reaches the clay
    bg2 = nt.nodes.new("ShaderNodeBackground")  # what the camera sees: soft white horizon
    bg2.inputs[0].default_value = (1, 1, 1, 1)
    bg2.inputs[1].default_value = 1.25
    lp = nt.nodes.new("ShaderNodeLightPath")
    mix = nt.nodes.new("ShaderNodeMixShader")
    out = nt.nodes["World Output"]
    nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs[0])
    nt.links.new(bg.outputs[0], mix.inputs[1])
    nt.links.new(bg2.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs[0])
    sun = bpy.data.lights.new("sun", "SUN")
    sun.energy = 5.0
    sun.angle = math.radians(9)  # soft clay shadows
    o = bpy.data.objects.new("sun", sun)
    o.rotation_euler = (math.radians(42), math.radians(8), math.radians(35))
    s.collection.objects.link(o)
    return s


def mat(name, color, rough=0.62, emit=0.0, alpha=1.0):
    key = (name, color, emit, alpha)
    if key in _mats:
        return _mats[key]
    m = bpy.data.materials.new(name)
    m.diffuse_color = color  # used by Workbench
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = color
    p.inputs["Roughness"].default_value = rough
    if emit:
        p.inputs["Emission Color"].default_value = color
        p.inputs["Emission Strength"].default_value = emit
    if alpha < 1:
        p.inputs["Alpha"].default_value = alpha
    _mats[key] = m
    return m


def _finish(o, color=WHITE, bevel=0.0, m=None, parent=None):
    o.data.materials.append(m or mat("clay", color))
    if bevel:
        b = o.modifiers.new("bev", "BEVEL")
        b.width = bevel
        b.segments = 3
        b.limit_method = "ANGLE"
    for p in o.data.polygons:
        p.use_smooth = True
    if parent:
        o.parent = parent
    return o


def box(loc, size, color=WHITE, bevel=0.06, m=None, parent=None, name="box"):
    bpy.ops.mesh.primitive_cube_add(location=loc)
    o = bpy.context.object
    o.name = name
    o.scale = (size[0] / 2, size[1] / 2, size[2] / 2)
    bpy.ops.object.transform_apply(scale=True)
    return _finish(o, color, bevel, m, parent)


def cyl(loc, r, h, color=WHITE, rot=(0, 0, 0), m=None, parent=None, verts=32, name="cyl"):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=h, location=loc, rotation=rot)
    o = bpy.context.object
    o.name = name
    return _finish(o, color, 0.02, m, parent)


def sphere(loc, r, color=WHITE, scale=(1, 1, 1), m=None, parent=None, name="sph"):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=loc, segments=32, ring_count=16)
    o = bpy.context.object
    o.name = name
    o.scale = scale
    return _finish(o, color, 0, m, parent)


def empty(name, loc=(0, 0, 0), parent=None):
    e = bpy.data.objects.new(name, None)
    e.location = loc
    bpy.context.scene.collection.objects.link(e)
    if parent:
        e.parent = parent
    return e


def ground(size=400):
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, 0, 0))
    return _finish(bpy.context.object, WHITE)


def road(x0, x1, y0, y1, dashes=True):
    """Flat road slab (slightly darker) with white center dashes."""
    box(((x0 + x1) / 2, (y0 + y1) / 2, 0.01), (x1 - x0, y1 - y0, 0.04), GROUND, bevel=0)
    if dashes:
        horiz = (x1 - x0) > (y1 - y0)
        L = (x1 - x0) if horiz else (y1 - y0)
        n = int(L / 4)
        for i in range(n):
            t = (i + 0.5) / n
            if horiz:
                box((x0 + t * L, (y0 + y1) / 2, 0.035), (1.6, 0.16, 0.02), WHITE, bevel=0)
            else:
                box(((x0 + x1) / 2, y0 + t * L, 0.035), (0.16, 1.6, 0.02), WHITE, bevel=0)


def building(x, y, w, d, h, windows=True):
    box((x, y, h / 2), (w, d, h), WHITE, bevel=0.12)
    if windows:  # shallow inset strips read as windows in clay
        floors = int(h / 3.2)
        for f in range(floors):
            z = 1.8 + f * 3.2
            for side in (-1, 1):
                box((x, y + side * (d / 2 + 0.01), z), (w * 0.8, 0.04, 1.1), (0.72, 0.72, 0.71, 1), bevel=0)


def tree(x, y, s=1.0):
    cyl((x, y, 0.9 * s), 0.12 * s, 1.8 * s)
    sphere((x, y, 2.3 * s), 1.0 * s, scale=(1, 1, 1.15))


def car(name, color=BLACK, length=4.3):
    """Simple sedan; local +X is forward. Returns root empty."""
    root = empty(name)
    m = mat(name + "_body", color, rough=0.35)
    box((0, 0, 0.62), (length, 1.8, 0.7), m=m, bevel=0.18, parent=root)
    box((-0.25, 0, 1.22), (length * 0.52, 1.6, 0.6), m=m, bevel=0.2, parent=root)
    glass = mat("cglass", (0.06, 0.065, 0.075, 1), rough=0.1)
    box((-0.25, 0, 1.26), (length * 0.5, 1.63, 0.34), m=glass, bevel=0.08, parent=root)
    for fx in (1.35, -1.35):
        for fy in (0.82, -0.82):
            cyl((fx, fy, 0.36), 0.36, 0.28, rot=(math.pi / 2, 0, 0), m=mat("tyre", (0.3, 0.3, 0.3, 1)), parent=root)
    return root


def bus(name="bus", length=11.0):
    root = empty(name)
    box((0, 0, 1.75), (length, 2.5, 2.9), bevel=0.25, parent=root)
    glass = mat("glass", (0.25, 0.27, 0.3, 1), rough=0.15)
    for side in (-1, 1):
        box((0.3, side * 1.26, 2.15), (length * 0.82, 0.04, 1.0), m=glass, bevel=0, parent=root)
    box((length / 2 + 0.01, 0, 2.15), (0.04, 2.2, 1.2), m=glass, bevel=0, parent=root)
    for fx in (length * 0.32, -length * 0.32):
        for fy in (1.1, -1.1):
            cyl((fx, fy, 0.48), 0.48, 0.35, rot=(math.pi / 2, 0, 0), m=mat("tyre", (0.3, 0.3, 0.3, 1)), parent=root)
    return root


def figure(name, height=1.65, color=WHITE, slim=1.0):
    """Faceless mannequin. Returns dict of root + limb pivots for walk()."""
    k = height / 1.75
    root = empty(name)
    body = empty(name + "_body", parent=root)
    m = mat(name + "_m", color)
    sphere((0, 0, 1.60 * k), 0.13 * k, scale=(0.9, 0.9, 1.1), m=m, parent=body)        # head (no face)
    cyl((0, 0, 1.44 * k), 0.05 * k, 0.12 * k, m=m, parent=body)                          # neck
    sphere((0, 0, 1.17 * k), 0.2 * k, scale=(0.75 * slim, 1.0 * slim, 1.55), m=m, parent=body)  # torso
    sphere((0, 0, 0.9 * k), 0.17 * k, scale=(0.8, 1.0, 0.7), m=m, parent=body)          # hips
    piv = {}
    for side, yy in (("L", 0.09), ("R", -0.09)):
        hip = empty(f"{name}_leg{side}", (0, yy * k, 0.88 * k), parent=body)
        cyl((0, 0, -0.42 * k), 0.065 * k, 0.84 * k, m=m, parent=hip)
        sphere((0.05 * k, 0, -0.86 * k), 0.07 * k, scale=(1.6, 0.9, 0.6), m=m, parent=hip)
        piv["leg" + side] = hip
        sh = empty(f"{name}_arm{side}", (0, yy * 2.1 * k, 1.38 * k), parent=body)
        cyl((0, 0, -0.3 * k), 0.045 * k, 0.6 * k, m=m, parent=sh)
        sphere((0, 0, -0.62 * k), 0.05 * k, m=m, parent=sh)
        piv["arm" + side] = sh
    return {"root": root, "body": body, **piv}


def _interp(keys, f):
    """keys: list of (frame, value-tuple) ; linear interpolation with smoothstep inside segments."""
    if f <= keys[0][0]:
        return Vector(keys[0][1])
    for (f0, v0), (f1, v1) in zip(keys, keys[1:]):
        if f0 <= f <= f1:
            t = (f - f0) / max(1e-6, f1 - f0)
            return Vector(v0).lerp(Vector(v1), t)
    return Vector(keys[-1][1])


def path_xy(keys, f, ease=False):
    if ease:
        for (f0, v0), (f1, v1) in zip(keys, keys[1:]):
            if f0 <= f <= f1:
                t = (f - f0) / max(1e-6, f1 - f0)
                t = t * t * (3 - 2 * t)
                return Vector(v0).lerp(Vector(v1), t)
    return _interp(keys, f)


def animate_mover(obj, keys, f0, f1, ease=False, face=True, z=0.0):
    """Keyframe location (and heading) of obj every frame along keys [(frame,(x,y)),...]."""
    prev = None
    yaw = 0.0
    for f in range(f0, f1 + 1):
        p = path_xy(keys, f, ease)
        obj.location = (p.x, p.y, z)
        obj.keyframe_insert("location", frame=f)
        if face and prev is not None and (p - prev).length > 1e-4:
            yaw = math.atan2(p.y - prev.y, p.x - prev.x)
        if face:
            obj.rotation_euler = (0, 0, yaw)
            obj.keyframe_insert("rotation_euler", frame=f)
        prev = p


def walk(fig, keys, f0, f1, stride=1.3, run=False):
    """Move a figure along keys and swing limbs according to its speed."""
    animate_mover(fig["root"], keys, f0, f1)
    phase = 0.0
    prev = path_xy(keys, f0)
    amp_l, amp_a = (0.75, 0.9) if run else (0.45, 0.4)
    for f in range(f0, f1 + 1):
        p = path_xy(keys, f)
        v = (p - prev).length
        prev = p
        phase += v / stride * math.pi
        mv = min(1.0, v * FPS / 1.2)  # 0 when standing
        s = math.sin(phase)
        fig["legL"].rotation_euler = (0, amp_l * mv * s, 0)
        fig["legR"].rotation_euler = (0, -amp_l * mv * s, 0)
        fig["armL"].rotation_euler = (0, -amp_a * mv * s, 0)
        fig["armR"].rotation_euler = (0, amp_a * mv * s, 0)
        fig["body"].location = (0, 0, 0.03 * mv * abs(math.cos(phase)))
        for k in ("legL", "legR", "armL", "armR"):
            fig[k].keyframe_insert("rotation_euler", frame=f)
        fig["body"].keyframe_insert("location", frame=f)


def visible(obj, frames_on_off):
    """frames_on_off: list of (frame, bool). Applies to obj and all children."""
    objs = [obj] + list(obj.children_recursive)
    for f, on in frames_on_off:
        for o in objs:
            o.hide_render = not on
            o.hide_viewport = not on
            o.keyframe_insert("hide_render", frame=f)
            o.keyframe_insert("hide_viewport", frame=f)


def trail(name, pts, color=ACCENT, width=0.12, z=0.06, grow=None, emit=0.6):
    """Route line on the ground; grow=(f0,f1) animates drawing it."""
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    sp = cu.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    for i, (x, y) in enumerate(pts):
        sp.points[i].co = (x, y, z, 1)
    cu.bevel_depth = width
    cu.bevel_resolution = 2
    o = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(o)
    o.data.materials.append(mat(name + "_m", color, emit=emit))
    if grow:
        cu.bevel_factor_end = 0.0
        cu.keyframe_insert("bevel_factor_end", frame=grow[0])
        cu.bevel_factor_end = 1.0
        cu.keyframe_insert("bevel_factor_end", frame=grow[1])
    return o


def camera(lens=32):
    cd = bpy.data.cameras.new("cam")
    cd.lens = lens
    cam = bpy.data.objects.new("cam", cd)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    tgt = empty("cam_target")
    c = cam.constraints.new("TRACK_TO")
    c.target = tgt
    c.track_axis = "TRACK_NEGATIVE_Z"
    c.up_axis = "UP_Y"
    return cam, tgt


def key_smooth(obj, keys, path="location"):
    """keys: [(frame, (x,y,z))] with Bezier ease between keys (camera moves)."""
    for f, v in keys:
        setattr(obj, path, v)
        obj.keyframe_insert(path, frame=f)

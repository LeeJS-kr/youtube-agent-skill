"""PNG 프레임 폴더 -> mp4 (Blender VSE, H.264 고화질, 30fps). blender -b -P encode_seq.py -- <frames_dir> <out.mp4>"""
import bpy, os, sys
src, out = sys.argv[sys.argv.index("--") + 1:][:2]
fs = sorted(f for f in os.listdir(src) if f.endswith(".png") and not f.startswith("still"))
s = bpy.context.scene
s.sequence_editor_create()
st = s.sequence_editor.strips.new_image("seq", os.path.join(src, fs[0]), 1, 1) if hasattr(s.sequence_editor, "strips") else \
     s.sequence_editor.sequences.new_image("seq", os.path.join(src, fs[0]), 1, 1)
for f in fs[1:]: st.elements.append(f)
s.frame_start, s.frame_end = 1, len(fs)
s.render.fps = 30; s.render.resolution_x, s.render.resolution_y = 1920, 1080; s.render.resolution_percentage = 100
s.render.image_settings.file_format = "FFMPEG"
s.render.ffmpeg.format = "MPEG4"; s.render.ffmpeg.codec = "H264"
s.render.ffmpeg.constant_rate_factor = "HIGH"; s.render.ffmpeg.ffmpeg_preset = "GOOD"
s.view_settings.view_transform = "Standard"
s.render.filepath = out
bpy.ops.render.render(animation=True)
print("ENCODED", out, len(fs))

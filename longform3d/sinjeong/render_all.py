"""PC(RTX 3080)용 일괄 렌더: python render_all.py "E:\\claude 3d\\blender-4.5.17-windows-x64\\blender.exe" [scene ...]
각 장면을 1920x1080, Cycles GPU(OptiX)로 PNG 프레임 렌더 후, Blender 자체 인코더로 mp4(H.264) 묶음.
결과: out/<scene>.mp4 , 로그: out/render_log.txt (장면별 걸린 시간)"""
import os, sys, subprocess, time
HERE = os.path.dirname(os.path.abspath(__file__))
BL = sys.argv[1]
SCENES = sys.argv[2:] or ["op_alley", "op_route", "op_window", "map", "banjiha_stairs", "shoe_cabinet", "shoe_off",
                          "section", "section_clinic", "b2_stairs"]
SAMPLES = int(os.environ.get("SJ_SAMPLES", "96"))
OUT = os.path.join(HERE, "out"); os.makedirs(OUT, exist_ok=True)
ENC = os.path.join(HERE, "encode_seq.py")
for sc in SCENES:
    t = time.time()
    subprocess.run([BL, "-b", "-P", os.path.join(HERE, "sinjeong3d.py"), "--", "--scene", sc, "--out", os.path.join(OUT, "frames"),
                    "--res", "1920x1080", "--samples", str(SAMPLES), "--gpu"], check=True)
    subprocess.run([BL, "-b", "-P", ENC, "--", os.path.join(OUT, "frames", sc), os.path.join(OUT, sc + ".mp4")], check=True)
    msg = f"{sc}: {time.time() - t:.0f}s"
    print(msg, flush=True); open(os.path.join(OUT, "render_log.txt"), "a").write(msg + "\n")

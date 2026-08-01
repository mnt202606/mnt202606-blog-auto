import json
import re
import subprocess
import sys
from pathlib import Path

from PIL import ImageFont

BASE = Path(__file__).parent
ASSETS = BASE / "assets"
CAPTIONS = BASE / "captions"

ASS_FONT = "Black Han Sans"
ASS_FONT_FILE = ASSETS / "BlackHanSans-Regular.ttf"
BASE_COLOR = "FFFFFF"     # white, ASS BGR order handled below
HIGHLIGHT_COLOR = "0044FF"  # vivid orange-red (#FF4400) in BGR order
HEADER_COLOR = "00E1FF"   # yellow (#FFE100) in BGR order

W, H, FPS = 1080, 1920, 25
TARGET_TEXT_WIDTH = 1020  # px, how wide a line should stretch to (near edge-to-edge)


def strip_markup(line):
    line = re.sub(r"\{\\fs\d+\}", "", line)
    line = re.sub(r"\{\{(.*?)\}\}", r"\1", line)
    line = re.sub(r"\[\[(.*?)\]\]", r"\1", line)
    return line


def autofit_fontsize(caption, target_width=TARGET_TEXT_WIDTH, min_size=80, max_size=230):
    ref_size = 200
    font = ImageFont.truetype(str(ASS_FONT_FILE), ref_size)
    lines = [strip_markup(l) for l in caption.split("\n") if strip_markup(l).strip()]
    max_w = max(font.getlength(l) for l in lines)
    size = int(ref_size * (target_width / max_w))
    return max(min_size, min(max_size, size))


def ass_time(seconds):
    cs = round(seconds * 100)
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def build_ass_text(caption, base_color):
    lines = caption.split("\n")
    out_lines = []
    for line in lines:
        parts = re.split(r"(\{\{.*?\}\}|\[\[.*?\]\])", line)
        buf = ""
        for part in parts:
            if part.startswith("{{") and part.endswith("}}"):
                word = part[2:-2]
                buf += f"{{\\c&H{HIGHLIGHT_COLOR}&}}{word}{{\\c&H{base_color}&}}"
            elif part.startswith("[[") and part.endswith("]]"):
                word = part[2:-2]
                buf += f"{{\\c&H{HEADER_COLOR}&}}{word}{{\\c&H{base_color}&}}"
            else:
                buf += part
        out_lines.append(buf)
    return "\\N".join(out_lines)


def write_ass(caption, duration, out_path, base_color=BASE_COLOR, fontsize=96, margin_v=340):
    text = "{\\c&H" + base_color + "&}" + build_ass_text(caption, base_color)
    content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{ASS_FONT},{fontsize},&H00{base_color},&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,7,3,2,60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,{ass_time(0)},{ass_time(duration)},Default,,0,0,0,,{text}
"""
    out_path.write_text(content, encoding="utf-8")

def run(cmd):
    print(">>", " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(BASE), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        print(result.stdout[-3000:])
        print(result.stderr[-3000:])
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")
    return result.stdout


VOICE = "ko-KR-InJoonNeural"


def build_scene_audio(clauses, out_mp3, scene_id):
    # One continuous edge-tts synthesis per scene - no internal joins, so there
    # is no seam to sound unnatural. Manual per-clause emphasis (separate calls
    # glued back together) kept producing audible seams no matter how the join
    # was smoothed, so we rely on the voice's own sentence-level intonation
    # instead, with a single modest speed bump for pacing.
    text = " ".join(clause_text for clause_text, _ in clauses)
    txt_path = out_mp3.with_suffix(".txt")
    txt_path.write_text(text, encoding="utf-8")
    run([
        "edge-tts",
        "--voice", VOICE,
        "--rate", "+9%",
        "--file", str(txt_path.relative_to(BASE)).replace("\\", "/"),
        "--write-media", str(out_mp3.relative_to(BASE)).replace("\\", "/"),
    ])


def get_duration(path):
    out = run([
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-of", "csv=p=0", str(path.relative_to(BASE)).replace("\\", "/"),
    ])
    return float(out.strip())


def build_segment(scene, audio_path, duration, out_path):
    ass_path = CAPTIONS / f"scene_{scene['id']}.ass"

    pad = 0.35
    total = duration + pad
    frames = max(1, round(total * FPS))

    fontsize = scene.get("fontsize") or autofit_fontsize(scene["caption"])
    write_ass(
        scene["caption"], total, ass_path,
        base_color=scene.get("base_color", BASE_COLOR),
        fontsize=fontsize,
        margin_v=scene.get("margin_v", 340),
    )

    if scene["zoom"] == "in":
        zexpr = "min(zoom+0.0012,1.18)"
    else:
        zexpr = "max(1.18-on*0.0012,1.0)"

    sw, sh = W * 2, H * 2

    vf = (
        f"scale={sw}:{sh}:force_original_aspect_ratio=increase,"
        f"crop={sw}:{sh},"
        f"zoompan=z='{zexpr}':d={frames}:s={W}x{H}:fps={FPS},"
        f"format=yuv420p,"
        f"subtitles=filename={ass_path.relative_to(BASE).as_posix()}:fontsdir=assets"
    )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", scene["image"],
        "-i", str(audio_path.relative_to(BASE)).replace("\\", "/"),
        "-filter_complex", f"[0:v]{vf}[v]",
        "-map", "[v]", "-map", "1:a",
        "-t", str(total),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-r", str(FPS),
        str(out_path.relative_to(BASE)).replace("\\", "/"),
    ]
    run(cmd)


def main():
    scenes = json.loads((BASE / "scenes.json").read_text(encoding="utf-8"))
    ASSETS.mkdir(exist_ok=True)
    CAPTIONS.mkdir(exist_ok=True)

    only_ids = {int(a) for a in sys.argv[1:]} if len(sys.argv) > 1 else None

    segment_paths = []
    for scene in scenes:
        audio_path = ASSETS / f"audio_{scene['id']}.mp3"
        seg_path = ASSETS / f"segment_{scene['id']}.mp4"
        if only_ids is None or scene["id"] in only_ids:
            print(f"\n=== Scene {scene['id']} ===")
            if not audio_path.exists():
                build_scene_audio(scene["narration_clauses"], audio_path, scene["id"])
            duration = get_duration(audio_path)
            print(f"duration: {duration:.2f}s")
            build_segment(scene, audio_path, duration, seg_path)
        segment_paths.append(seg_path)

    concat_list = ASSETS / "concat.txt"
    concat_list.write_text(
        "\n".join(f"file '{p.name}'" for p in segment_paths),
        encoding="utf-8",
    )

    final_out = BASE / "pokyeom_shorts.mp4"
    run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list.relative_to(BASE)).replace("\\", "/"),
        "-c", "copy",
        str(final_out.relative_to(BASE)).replace("\\", "/"),
    ])
    print(f"\nDONE: {final_out}")


if __name__ == "__main__":
    main()

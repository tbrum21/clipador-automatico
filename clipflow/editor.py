"""Monta o video vertical 9:16: fundo desfocado, gameplay, facecam opcional, zoom, legenda e audio."""
import json
import subprocess
from pathlib import Path
from typing import Optional

from . import config as C

W, H = 1080, 1920
GAME_H = 608  # 1080 x 608 (16:9)
CAM_H = 600


def load_template(name: str) -> dict:
    data = json.loads(C.TEMPLATES_PATH.read_text(encoding="utf-8"))
    return data.get(name) or data["default"]


def _encoder_args() -> list[str]:
    if C.ENCODER == "h264_amf":
        return ["-c:v", "h264_amf", "-quality", "quality", "-b:v", "10M", "-maxrate", "14M"]
    return ["-c:v", "libx264", "-preset", "fast", "-crf", "20"]


def build_filter(template: dict, ass_name: str, zoom_at: Optional[float],
                 orientation: str = 'vertical', background: str = 'blur') -> tuple[str, int]:
    if orientation not in ('vertical', 'horizontal') or background not in ('blur', 'black'):
        raise ValueError('Formato ou fundo invalido')
    if orientation == 'horizontal':
        # Mantem todo o quadro original, inclusive a facecam ja presente na transmissao.
        w, h = 1920, 1080
        bg = (f'scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},'
              'boxblur=40:5,eq=brightness=-0.12' if background == 'blur' else
              f'scale={w}:{h},drawbox=color=black:t=fill')
        zoom = (f",scale=w='trunc(iw*(1+0.12*max(0,1-abs(t-{zoom_at:.2f})/0.5))/2)*2':"
                f"h='trunc(ih*(1+0.12*max(0,1-abs(t-{zoom_at:.2f})/0.5))/2)*2':eval=frame"
                if zoom_at is not None and zoom_at >= 0 else '')
        graph = (f'[0:v]split=2[s0][s1];[s0]{bg}[bg];'
                 f'[s1]scale={w}:{h}:force_original_aspect_ratio=decrease:force_divisible_by=2{zoom}[game];'
                 f'[bg][game]overlay=(W-w)/2:(H-h)/2,ass={ass_name}[vout]')
        return graph, 95
    cam = template.get("facecam")
    game_y = 780 if cam else (H - GAME_H) // 2
    margin_v = 380

    game = (f"scale={W}:{GAME_H}:force_original_aspect_ratio=decrease:force_divisible_by=2,"
            f"pad={W}:{GAME_H}:(ow-iw)/2:(oh-ih)/2:color=black")
    if zoom_at is not None and zoom_at >= 0:
        game += (f",scale=w='trunc({W}*(1+0.12*max(0,1-abs(t-{zoom_at:.2f})/0.5))/2)*2':"
                 f"h='trunc({GAME_H}*(1+0.12*max(0,1-abs(t-{zoom_at:.2f})/0.5))/2)*2':eval=frame,"
                 f"crop={W}:{GAME_H}")

    n = 3 if cam else 2
    labels = "".join(f"[s{i}]" for i in range(n))
    bg = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=40:5,eq=brightness=-0.12"
          if background == 'blur' else f"scale={W}:{H},drawbox=color=black:t=fill")
    g = [f"[0:v]split={n}{labels}",
         f"[s0]{bg}[bg]",
         f"[s1]{game}[game]",
         f"[bg][game]overlay=0:{game_y}[v1]"]
    last = "v1"
    if cam:
        g.append(f"[s2]crop=iw*{cam['w']}:ih*{cam['h']}:iw*{cam['x']}:ih*{cam['y']},scale=-2:{CAM_H}[cam]")
        g.append(f"[v1][cam]overlay=(W-w)/2:110[v2]")
        last = "v2"
    g.append(f"[{last}]ass={ass_name}[vout]")
    return ";".join(g), margin_v


def render(raw: Path, start: float, dur: float, ass_name: str, workdir: Path, out: Path,
           template: dict, zoom_at: Optional[float], orientation: str = 'vertical', background: str = 'blur'):
    """Roda dentro de workdir para o filtro `ass` nao sofrer com 'C:\\' no caminho."""
    graph, _ = build_filter(template, ass_name, zoom_at, orientation, background)
    cmd = [C.FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
           "-ss", f"{start:.2f}", "-t", f"{dur:.2f}", "-i", raw.name,
           "-filter_complex", graph, "-map", "[vout]", "-map", "0:a?",
           "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
           *_encoder_args(), "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True, cwd=workdir)


def make_preview(src: Path, dst: Path, orientation: str = 'vertical'):
    """Copia leve na proporcao da saida; o tamanho final depende da duracao."""
    dimensions = '960:540' if orientation == 'horizontal' else '540:960'
    subprocess.run([C.FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
                    "-vf", f"scale={dimensions}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "27",
                    "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(dst)], check=True)

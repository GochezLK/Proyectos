from pathlib import Path


VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".m4v",
}


def get_partido_dir(video_path):
    """Devuelve la carpeta del partido a partir de la ruta del video."""
    return Path(video_path).resolve().parent


def get_resultados_dir(video_path):
    """Resultados/<video>/ dentro de la carpeta del partido."""
    video_path = Path(video_path).resolve()
    partido_dir = get_partido_dir(video_path)

    return partido_dir / "Resultados" / video_path.stem


def get_clips_dir(video_path):
    """Carpeta Clips del partido."""
    partido_dir = get_partido_dir(video_path)

    return partido_dir / "Clips"


def prepare_partido_dirs(video_path):
    """Crea las carpetas necesarias para procesar un video."""
    resultados_dir = get_resultados_dir(video_path)
    clips_dir = get_clips_dir(video_path)

    resultados_dir.mkdir(parents=True, exist_ok=True)
    clips_dir.mkdir(parents=True, exist_ok=True)

    return resultados_dir, clips_dir

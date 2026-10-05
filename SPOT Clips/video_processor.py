import os
import json
import sys
import cv2
import torch
import numpy as np

from types import SimpleNamespace
from model.model import TDEEDModel


# ============================================================
# CONFIGURACIÓN
# ============================================================

VIDEO = sys.argv[1] if len(sys.argv) > 1 else None

if VIDEO is None:
    raise ValueError(
        "Debes indicar el video. Ejemplo:\n"
        'python video_processor.py "C:\\ruta\\video.mp4"'
    )

CHECKPOINT = r".\checkpoints\checkpoint_best.pt"

# Video seleccionado
VIDEO_PATH = os.path.abspath(VIDEO)
VIDEO_DIR = os.path.dirname(VIDEO_PATH)
VIDEO_NAME = os.path.splitext(os.path.basename(VIDEO_PATH))[0]

# Carpeta de resultados del partido
OUTPUT_DIR = os.path.join(
    VIDEO_DIR,
    "Resultados",
)

# El modelo trabaja con clips de 100 frames
CLIP_LEN = 100

# Solapamiento.
# 50 significa:
# 0-99
# 50-149
# 100-199
# etc.
STRIDE = 50

# Resolución que utiliza el pipeline de SoccerNet Ball
MODEL_WIDTH = 796
MODEL_HEIGHT = 448

# Score mínimo para guardar un candidato.
#
# Lo dejamos relativamente bajo inicialmente porque estamos
# probando el comportamiento del modelo.
MIN_SCORE = 0.05

# Guardar avances parciales para videos largos. Esto permite recuperar
# detecciones si el proceso se cancela o falla antes de terminar.
PARTIAL_SAVE_EVERY_WINDOWS = 25


# ============================================================
# CLASES
# ============================================================

CLASSES = [
    "BACKGROUND",

    "PASS",
    "DRIVE",
    "HEADER",
    "HIGH PASS",
    "OUT",
    "CROSS",
    "THROW IN",
    "SHOT",
    "BALL PLAYER BLOCK",
    "PLAYER SUCCESSFUL TACKLE",
    "FREE KICK",
    "GOAL",
]


# ============================================================
# CONFIGURACIÓN DEL MODELO
# ============================================================

args = SimpleNamespace(
    temporal_arch="ed_sgp_mixer",
    feature_arch="rny002_gsf",
    clip_len=CLIP_LEN,
    crop_dim=None,
    radi_displacement=4,
    event_team=True,
    num_classes=12,
    n_layers=2,
    sgp_ks=9,
    sgp_r=4,
    modality="rgb",
)


# ============================================================
# UTILIDADES
# ============================================================

def format_time(seconds):
    """Convierte segundos a HH:MM:SS.mmm."""

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60

    return (
        f"{hours:02d}:"
        f"{minutes:02d}:"
        f"{secs:06.3f}"
    )


def get_event_name(class_index):
    """
    Convierte las 25 salidas del modelo en:

        evento + lado del equipo

    0 = background

    1,2   = PASS
    3,4   = DRIVE
    5,6   = HEADER
    ...

    Todavía no llamamos a los lados Equipo 1/Equipo 2.
    """

    if class_index == 0:
        return "BACKGROUND", None

    event_index = (class_index - 1) // 2
    team_side = (class_index - 1) % 2

    if event_index >= len(CLASSES) - 1:
        return "UNKNOWN", team_side

    event_name = CLASSES[event_index + 1]

    return event_name, team_side


def save_raw_results(
    output_file,
    fps,
    width,
    height,
    total_frames,
    duration,
    events,
    partial,
    processed_windows,
    last_frame,
):
    result = {
        "video": os.path.basename(
            VIDEO
        ),
        "source": os.path.abspath(
            VIDEO
        ),
        "fps": fps,
        "width": width,
        "height": height,
        "total_frames": total_frames,
        "duration": round(
            duration,
            3,
        ),
        "model": {
            "name": "SoccerNet TeamSpotting",
            "clip_len": CLIP_LEN,
            "stride": STRIDE,
            "input_width": MODEL_WIDTH,
            "input_height": MODEL_HEIGHT,
            "min_score": MIN_SCORE,
        },
        "processing_state": {
            "partial": partial,
            "processed_windows": processed_windows,
            "last_frame": last_frame,
        },
        "events": events,
    }

    temp_file = f"{output_file}.tmp"

    with open(
        temp_file,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            result,
            f,
            ensure_ascii=False,
            indent=2,
        )

    os.replace(
        temp_file,
        output_file,
    )


# ============================================================
# CREAR MODELO
# ============================================================

def create_model(device):

    print()
    print("========================================")
    print("CARGANDO MODELO")
    print("========================================")

    model = TDEEDModel(
        device=device,
        args=args,
    )

    # El checkpoint utiliza:
    #
    # 13 clases en la primera cabeza
    # 18 clases en la segunda cabeza
    #
    model._model.update_pred_head([13, 18])

    model._num_classes = 31

    checkpoint = torch.load(
        CHECKPOINT,
        map_location=device,
        weights_only=True,
    )

    model.load(checkpoint)

    print("Checkpoint cargado correctamente.")

    return model


# ============================================================
# LEER FRAME Y PREPROCESAR
# ============================================================

def preprocess_frame(frame):
    """
    OpenCV:
        BGR
        HWC

    Modelo:
        RGB
        CHW
    """

    frame = cv2.resize(
        frame,
        (MODEL_WIDTH, MODEL_HEIGHT),
        interpolation=cv2.INTER_AREA,
    )

    frame = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2RGB,
    )

    frame = torch.from_numpy(
        frame
    ).permute(2, 0, 1)

    return frame


# ============================================================
# PROCESAR UNA VENTANA
# ============================================================

def process_window(
    model,
    frames,
    start_frame,
    fps,
):
    """
    Procesa una ventana de CLIP_LEN frames.

    Devuelve los candidatos cuyo score supera MIN_SCORE.
    """

    tensor = torch.stack(frames)

    pred_cls, pred = model.predict(
        tensor
    )

    scores = pred[0]

    candidates = []

    for class_index in range(1, 25):

        frame_index = int(
            np.argmax(
                scores[:, class_index]
            )
        )

        score = float(
            scores[
                frame_index,
                class_index,
            ]
        )

        if score < MIN_SCORE:
            continue

        absolute_frame = (
            start_frame + frame_index
        )

        time_seconds = (
            absolute_frame / fps
        )

        event_name, team_side = (
            get_event_name(class_index)
        )

        candidates.append(
            {
                "frame": absolute_frame,
                "time": round(
                    time_seconds,
                    3,
                ),
                "timestamp": format_time(
                    time_seconds
                ),
                "event": event_name,
                "team_side": team_side,
                "class_index": class_index,
                "score": round(
                    score,
                    6,
                ),
            }
        )

    return candidates


# ============================================================
# PROCESAR VIDEO
# ============================================================

def process_video():

    device = (
        "cuda"
        if torch.cuda.is_available()
        else "cpu"
    )

    print("Device:", device)

    model = create_model(
        device
    )

    # --------------------------------------------------------
    # Abrir video
    # --------------------------------------------------------

    cap = cv2.VideoCapture(
        VIDEO
    )

    if not cap.isOpened():
        raise RuntimeError(
            f"No se pudo abrir el video:\n{VIDEO}"
        )

    fps = cap.get(
        cv2.CAP_PROP_FPS
    )

    total_frames = int(
        cap.get(
            cv2.CAP_PROP_FRAME_COUNT
        )
    )

    width = int(
        cap.get(
            cv2.CAP_PROP_FRAME_WIDTH
        )
    )

    height = int(
        cap.get(
            cv2.CAP_PROP_FRAME_HEIGHT
        )
    )

    duration = (
        total_frames / fps
        if fps > 0
        else 0
    )

    print()
    print("========================================")
    print("VIDEO")
    print("========================================")

    print(
        f"Archivo: {os.path.basename(VIDEO)}"
    )

    print(
        f"Resolución: {width}x{height}"
    )

    print(
        f"FPS: {fps}"
    )

    print(
        f"Frames: {total_frames}"
    )

    print(
        f"Duración: {duration:.2f} segundos"
    )

    print(
        f"Ventana: {CLIP_LEN} frames"
    )

    print(
        f"Stride: {STRIDE} frames"
    )

    print(
        f"Score mínimo: {MIN_SCORE}"
    )

    video_name = os.path.splitext(
        os.path.basename(VIDEO)
    )[0]

    result_dir = os.path.join(
        OUTPUT_DIR,
        video_name,
    )

    os.makedirs(
        result_dir,
        exist_ok=True,
    )

    output_file = os.path.join(
        result_dir,
        "events_raw.json",
    )

    # --------------------------------------------------------
    # Leer todos los frames necesarios para trabajar
    # por ventanas.
    #
    # NO se manda todo el video a la GPU.
    # --------------------------------------------------------

    frames_cache = {}
    next_frame_to_read = 0

    def read_until(target_frame):

        nonlocal next_frame_to_read

        while next_frame_to_read <= target_frame:

            ok, frame = cap.read()

            if not ok:
                return False

            processed = preprocess_frame(
                frame
            )

            frames_cache[
                next_frame_to_read
            ] = processed

            next_frame_to_read += 1

        return True


    def get_window(start_frame):

        end_frame = (
            start_frame + CLIP_LEN - 1
        )

        if not read_until(end_frame):
            return None

        frames = [
            frames_cache[frame_number]
            for frame_number in range(
                start_frame,
                end_frame + 1,
            )
        ]

        return frames

    # --------------------------------------------------------
    # Procesamiento
    # --------------------------------------------------------

    all_candidates = []

    window_number = 0

    start_frame = 0
    last_processed_frame = -1

    while (
        start_frame + CLIP_LEN
        <= total_frames
    ):

        window_number += 1

        end_frame = (
            start_frame + CLIP_LEN - 1
        )

        start_time = (
            start_frame / fps
        )

        end_time = (
            end_frame / fps
        )

        print()
        print(
            "----------------------------------------"
        )

        print(
            f"Ventana {window_number}"
        )

        print(
            f"Frames: "
            f"{start_frame}-{end_frame}"
        )

        print(
            f"Tiempo: "
            f"{format_time(start_time)} -> "
            f"{format_time(end_time)}"
        )

        # ------------------------------------
        # Cargar ventana
        # ------------------------------------

        frames = get_window(
            start_frame
        )

        if frames is None or len(frames) != CLIP_LEN:

            print(
                "No se pudo completar la ventana."
            )

            break

        # ------------------------------------
        # Inferencia
        # ------------------------------------

        candidates = process_window(
            model=model,
            frames=frames,
            start_frame=start_frame,
            fps=fps,
        )

        # ------------------------------------
        # Mostrar candidatos
        # ------------------------------------

        if candidates:

            candidates.sort(
                key=lambda x: x["score"],
                reverse=True,
            )

            for candidate in candidates:

                print(
                    f"  {candidate['timestamp']} | "
                    f"{candidate['event']:30s} | "
                    f"side={candidate['team_side']} | "
                    f"score={candidate['score']:.4f}"
                )

            all_candidates.extend(
                candidates
            )

        else:

            print(
                "  Sin eventos por encima "
                f"de {MIN_SCORE:.2f}"
            )

        # ------------------------------------
        # Siguiente ventana
        # ------------------------------------

        start_frame += STRIDE

        # ------------------------------------
        # Liberar memoria GPU
        # ------------------------------------

        if device == "cuda":
            torch.cuda.empty_cache()

        last_processed_frame = end_frame

        if window_number % PARTIAL_SAVE_EVERY_WINDOWS == 0:
            save_raw_results(
                output_file=output_file,
                fps=fps,
                width=width,
                height=height,
                total_frames=total_frames,
                duration=duration,
                events=all_candidates,
                partial=True,
                processed_windows=window_number,
                last_frame=last_processed_frame,
            )

            print(
                f"Avance guardado: {output_file}"
            )

    cap.release()

    # ========================================================
    # GUARDAR RESULTADOS
    # ========================================================
    save_raw_results(
        output_file=output_file,
        fps=fps,
        width=width,
        height=height,
        total_frames=total_frames,
        duration=duration,
        events=all_candidates,
        partial=False,
        processed_windows=window_number,
        last_frame=last_processed_frame,
    )

    # ========================================================
    # RESUMEN
    # ========================================================

    print()
    print("========================================")
    print("PROCESAMIENTO TERMINADO")
    print("========================================")

    print(
        f"Candidatos encontrados: "
        f"{len(all_candidates)}"
    )

    print(
        f"Resultado:"
        f"\n{os.path.abspath(output_file)}"
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    process_video()

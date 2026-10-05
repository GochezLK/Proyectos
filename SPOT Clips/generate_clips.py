import json
import shutil
import subprocess
import sys
from pathlib import Path


# ========================================
# CONFIGURACIÓN
# ========================================

if len(sys.argv) < 2:
    raise ValueError(
        "Debes indicar el video."
    )

VIDEO_PATH = Path(sys.argv[1]).resolve()

PARTIDO_DIR = VIDEO_PATH.parent

RESULTS_DIR = (
    PARTIDO_DIR
    / "Resultados"
    / VIDEO_PATH.stem
)

SEQUENCES_FILE = RESULTS_DIR / "sequences.json"

CLIPS_DIR = PARTIDO_DIR / "Clips"

# Tiempo adicional antes y después de cada secuencia.
CONTEXT_BEFORE = 3
CONTEXT_AFTER = 3

# Si dos clips ya con contexto quedan separados por pocos segundos,
# se consideran la misma jugada continua.
MERGE_CLIP_GAP = 3

# Cortar antes de que FFmpeg deje archivos incompletos por falta de espacio.
MIN_FREE_GB = 8

# Salida más ligera para uso real. Mantiene NVENC, pero baja 4K a 1080p.
OUTPUT_MAX_WIDTH = 1920
OUTPUT_CQ = 28


# ========================================
# FUNCIONES
# ========================================

def format_timestamp(seconds):
    """Convierte segundos a HH-MM-SS-mmm."""
    total_ms = int(round(seconds * 1000))

    hours = total_ms // 3_600_000
    total_ms %= 3_600_000

    minutes = total_ms // 60_000
    total_ms %= 60_000

    secs = total_ms // 1000
    ms = total_ms % 1000

    return f"{hours:02d}-{minutes:02d}-{secs:02d}-{ms:03d}"


def safe_filename(text):
    return (
        text.replace(" ", "_")
        .replace("/", "_")
        .replace("\\", "_")
    )


def free_space_gb(path):
    usage = shutil.disk_usage(path)
    return usage.free / (1024 ** 3)


def ensure_free_space(path):
    free_gb = free_space_gb(path)

    if free_gb < MIN_FREE_GB:
        raise RuntimeError(
            "Espacio insuficiente para generar clips: "
            f"{free_gb:.2f} GB libres en {path.anchor}. "
            f"Libera al menos {MIN_FREE_GB} GB y vuelve a intentar."
        )


def sequence_clip_start(sequence):
    return max(
        0,
        float(sequence["start"]) - CONTEXT_BEFORE,
    )


def sequence_clip_end(sequence):
    return float(sequence["end"]) + CONTEXT_AFTER


def merge_overlapping_sequences(sequences):
    """
    Fusiona secuencias cuyos clips finales se solapan o quedan muy cerca.

    Ejemplo:

        SEQ 2: clip 05s - 25s
        SEQ 3: clip 28s - 35s

        Resultado:

        SEQ 2-3 si el hueco es <= MERGE_CLIP_GAP.
    """

    if not sequences:
        return []

    # Ordenar por tiempo de inicio.
    sequences = sorted(
        sequences,
        key=lambda sequence: float(sequence["start"])
    )

    merged = []

    current = dict(sequences[0])
    current["original_ids"] = [current["id"]]

    for sequence in sequences[1:]:

        start = float(sequence["start"])
        end = float(sequence["end"])
        clip_start = sequence_clip_start(sequence)
        current_clip_end = sequence_clip_end(current)

        # ----------------------------------------
        # Existe solapamiento o continuidad cercana
        # ----------------------------------------

        if clip_start <= current_clip_end + MERGE_CLIP_GAP:

            current["end"] = max(
                float(current["end"]),
                end,
            )

            current["original_ids"].extend(
                sequence.get("original_ids", [sequence["id"]])
            )

            # Conservar el evento principal
            # con mayor score.
            if (
                sequence["main_score"]
                > current["main_score"]
            ):
                current["main_event"] = (
                    sequence["main_event"]
                )

                current["main_score"] = (
                    sequence["main_score"]
                )

        else:

            # No se solapan.
            merged.append(current)

            current = dict(sequence)

            current["original_ids"] = [
                current["id"]
            ]

    # Agregar el último bloque.
    merged.append(current)

    return merged


def create_clip(sequence):
    sequence_id = sequence["id"]

    start_event = float(sequence["start"])
    end_event = float(sequence["end"])

    start = max(
        0,
        start_event - CONTEXT_BEFORE
    )

    end = end_event + CONTEXT_AFTER

    duration = end - start

    start_timestamp = format_timestamp(
        start_event
    )

    end_timestamp = format_timestamp(
        end_event
    )

    # ----------------------------------------
    # Nombre del clip
    # ----------------------------------------

    original_ids = sequence.get(
        "original_ids",
        [sequence_id]
    )

    if len(original_ids) > 1:

        ids_text = (
            f"SEQ{original_ids[0]:02d}"
            f"-"
            f"{original_ids[-1]:02d}"
        )

    else:

        ids_text = (
            f"SEQ{sequence_id:02d}"
        )

    filename = (
        f"{safe_filename(VIDEO_PATH.stem)}"
        f"_{ids_text}"
        f"_{start_timestamp}"
        f"_to_{end_timestamp}"
        f".mp4"
    )

    output_path = CLIPS_DIR / filename
    temp_output_path = output_path.with_name(
        f"{output_path.stem}.part{output_path.suffix}"
    )

    if output_path.exists() and output_path.stat().st_size > 0:
        print()
        print("-" * 50)
        print(f"Ya existe, saltando: {output_path.name}")
        return output_path

    ensure_free_space(CLIPS_DIR)

    if temp_output_path.exists():
        temp_output_path.unlink()

    command = [
        "ffmpeg",
        "-y",
    	"-hwaccel", "cuda",
    	"-hwaccel_output_format", "cuda",
    	"-ss", str(start),
    	"-i", str(VIDEO_PATH),
    	"-t", str(duration),
    	"-vf", f"scale_cuda=w={OUTPUT_MAX_WIDTH}:h=-2:format=yuv420p",
    	"-c:v", "h264_nvenc",
    	"-preset", "p5",
    	"-cq", str(OUTPUT_CQ),
    	"-c:a", "aac",
    	str(temp_output_path),
    ]
    print()
    print("-" * 50)

    if len(original_ids) > 1:
        print(
            f"Secuencias fusionadas: "
            f"{', '.join(str(x) for x in original_ids)}"
        )
    else:
        print(
            f"Secuencia : #{sequence_id}"
        )

    print(
        f"Eventos   : "
        f"{start_event:.3f}s -> "
        f"{end_event:.3f}s"
    )

    print(
        f"Clip      : "
        f"{start:.3f}s -> "
        f"{end:.3f}s"
    )

    print(
        f"Duración  : "
        f"{duration:.3f}s"
    )

    print(
        f"Principal : "
        f"{sequence['main_event']}"
    )

    print(
        f"Score     : "
        f"{sequence['main_score']:.4f}"
    )

    print(
        f"Salida    : "
        f"{output_path.name}"
    )

    try:
        subprocess.run(
            command,
            check=True
        )

        temp_output_path.replace(output_path)

    except Exception:
        if temp_output_path.exists():
            temp_output_path.unlink()
        raise

    return output_path


# ========================================
# MAIN
# ========================================

print("=" * 50)
print("GENERANDO CLIPS POR SECUENCIA")
print("=" * 50)

if not VIDEO_PATH.exists():
    raise FileNotFoundError(
        f"No se encontró el video:\n{VIDEO_PATH}"
    )

if not SEQUENCES_FILE.exists():
    raise FileNotFoundError(
        f"No se encontró sequences.json:\n"
        f"{SEQUENCES_FILE}"
    )

CLIPS_DIR.mkdir(
    parents=True,
    exist_ok=True
)

with open(
    SEQUENCES_FILE,
    "r",
    encoding="utf-8"
) as f:

    data = json.load(f)

sequences = data["sequences"]

# ----------------------------------------
# Secuencias originales
# ----------------------------------------

print(
    f"Secuencias originales: "
    f"{len(sequences)}"
)

# ----------------------------------------
# Fusionar secuencias que se solapen
# ----------------------------------------

sequences = merge_overlapping_sequences(
    sequences
)

print(
    f"Secuencias después de fusionar: "
    f"{len(sequences)}"
)

print(
    f"Contexto: "
    f"-{CONTEXT_BEFORE}s / "
    f"+{CONTEXT_AFTER}s"
)

print(
    f"Fusionar huecos de hasta: "
    f"{MERGE_CLIP_GAP}s"
)

print(
    f"Salida: max {OUTPUT_MAX_WIDTH}px ancho, "
    f"CQ {OUTPUT_CQ}"
)

print(
    f"Espacio libre requerido: "
    f"{MIN_FREE_GB} GB"
)

print(
    f"Directorio: {CLIPS_DIR}"
)

created = 0
failed = 0

# ----------------------------------------
# Generar clips
# ----------------------------------------

for sequence in sequences:

    try:

        create_clip(sequence)

        created += 1

    except subprocess.CalledProcessError as e:
        failed += 1

        print(
            f"ERROR FFmpeg: {e}"
        )

    except Exception as e:
        failed += 1

        print(
            f"ERROR: {e}"
        )


# ========================================
# RESUMEN
# ========================================

print()
print("=" * 50)
print("GENERACIÓN TERMINADA")
print("=" * 50)

print(
    f"Secuencias originales: "
    f"{len(data['sequences'])}"
)

print(
    f"Bloques después de fusionar: "
    f"{len(sequences)}"
)

print(
    f"Clips creados: {created}"
)

print(
    f"Clips con error: {failed}"
)

print("Ubicación:")

print(
    CLIPS_DIR.resolve()
)

if failed:
    sys.exit(1)

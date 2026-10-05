import json
import os
import sys

# ============================================================
# CONFIGURACIÓN
# ============================================================

if len(sys.argv) < 2:
    raise ValueError(
        "Debes indicar el nombre del video o su ruta."
    )

VIDEO_PATH = sys.argv[1]
VIDEO_NAME = os.path.splitext(
    os.path.basename(VIDEO_PATH)
)[0]

VIDEO_PATH_ABS = os.path.abspath(VIDEO_PATH)
VIDEO_DIR = os.path.dirname(VIDEO_PATH_ABS)

RESULTS_DIR = os.path.join(
    VIDEO_DIR,
    "Resultados",
    VIDEO_NAME,
)

INPUT_FILE = os.path.join(
    RESULTS_DIR,
    "events_raw.json",
)

OUTPUT_FILE = os.path.join(
    RESULTS_DIR,
    "events.json",
)

# ============================================================
# PARÁMETROS
# ============================================================

# Detecciones del MISMO evento dentro de este intervalo
# se consideran el mismo evento.
MERGE_WINDOW = 1.5


# ============================================================
# CARGAR
# ============================================================

print()
print("========================================")
print("CONSOLIDANDO EVENTOS")
print("========================================")

if not os.path.exists(INPUT_FILE):
    raise FileNotFoundError(
        f"No existe:\n{os.path.abspath(INPUT_FILE)}"
    )

with open(
    INPUT_FILE,
    "r",
    encoding="utf-8",
) as f:
    data = json.load(f)

raw_events = data.get("events", [])

print(
    f"Eventos originales: {len(raw_events)}"
)


# ============================================================
# ORDENAR
# ============================================================

raw_events.sort(
    key=lambda event: event["time"]
)


# ============================================================
# PRIMERA FASE
#
# Mismo evento + mismo equipo + cerca en tiempo
# ============================================================

groups = []

for event in raw_events:

    placed = False

    for group in groups:

        reference = group[-1]

        same_event = (
            event["event"]
            == reference["event"]
        )

        same_team = (
            event["team_side"]
            == reference["team_side"]
        )

        close = (
            abs(
                event["time"]
                - reference["time"]
            )
            <= MERGE_WINDOW
        )

        if (
            same_event
            and same_team
            and close
        ):
            group.append(event)
            placed = True
            break

    if not placed:
        groups.append([event])


# ============================================================
# ELEGIR EL MEJOR DE CADA GRUPO
# ============================================================

events = []

for group in groups:

    best = max(
        group,
        key=lambda event: event["score"]
    )

    events.append(best)


# ============================================================
# SEGUNDA FASE
#
# MISMO EVENTO + MUY CERCA EN TIEMPO
#
# Aquí NO importa el team_side.
#
# Ejemplo:
#
# 27.400 OUT side=0 score=0.19
# 27.400 OUT side=1 score=0.29
#
# queda:
#
# 27.400 OUT side=1 score=0.29
# ============================================================

events.sort(
    key=lambda event: event["time"]
)

final_events = []

for event in events:

    merged = False

    for i, existing in enumerate(
        final_events
    ):

        same_event = (
            event["event"]
            == existing["event"]
        )

        close = (
            abs(
                event["time"]
                - existing["time"]
            )
            <= MERGE_WINDOW
        )

        if same_event and close:

            # Conservar la detección
            # con mayor confianza.
            if event["score"] > existing["score"]:
                final_events[i] = event

            merged = True
            break

    if not merged:
        final_events.append(event)


# ============================================================
# ORDEN FINAL
# ============================================================

final_events.sort(
    key=lambda event: event["time"]
)


# ============================================================
# MOSTRAR
# ============================================================

print()
print("Eventos consolidados:")
print("----------------------------------------")

for index, event in enumerate(
    final_events,
    start=1,
):

    print(
        f"{index:02d}. "
        f"{event['timestamp']} | "
        f"{event['event']:30s} | "
        f"side={event['team_side']} | "
        f"score={event['score']:.4f}"
    )


# ============================================================
# RESULTADO
# ============================================================

result = {
    "video": data["video"],
    "source": data["source"],
    "fps": data["fps"],
    "width": data["width"],
    "height": data["height"],
    "total_frames": data["total_frames"],
    "duration": data["duration"],

    "processing": {
        "model": data["model"],
        "merge_window_seconds": MERGE_WINDOW,
        "raw_events": len(raw_events),
        "consolidated_events": len(final_events),
    },

    "events": final_events,
}


# ============================================================
# GUARDAR
# ============================================================

with open(
    OUTPUT_FILE,
    "w",
    encoding="utf-8",
) as f:

    json.dump(
        result,
        f,
        ensure_ascii=False,
        indent=2,
    )


# ============================================================
# RESUMEN
# ============================================================

print()
print("========================================")
print("CONSOLIDACIÓN TERMINADA")
print("========================================")

print(
    f"Eventos originales: "
    f"{len(raw_events)}"
)

print(
    f"Eventos consolidados: "
    f"{len(final_events)}"
)

print(
    f"Eliminados: "
    f"{len(raw_events) - len(final_events)}"
)

print()
print(
    f"Guardado en:\n"
    f"{os.path.abspath(OUTPUT_FILE)}"
)
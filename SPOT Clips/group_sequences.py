import json
from pathlib import Path
import sys


# ========================================
# CONFIGURACIÃ“N
# ========================================

if len(sys.argv) < 2:
    raise ValueError(
        "Debes indicar el nombre del video o su ruta."
    )

VIDEO_PATH = Path(sys.argv[1])
VIDEO_NAME = VIDEO_PATH.stem

VIDEO_PATH = VIDEO_PATH.resolve()

PARTIDO_DIR = VIDEO_PATH.parent

RESULTS_DIR = (
    PARTIDO_DIR
    / "Resultados"
    / VIDEO_NAME
)
EVENTS_FILE = RESULTS_DIR / "events.json"
SEQUENCES_FILE = RESULTS_DIR / "sequences.json"

# Si dos eventos estÃ¡n separados por <= 3 segundos,
# pertenecen a la misma secuencia.
MAX_GAP = 3.0


# ========================================
# FUNCIONES
# ========================================

def group_events(events):
    if not events:
        return []

    # Aseguramos orden temporal
    events = sorted(events, key=lambda x: float(x["time"]))

    sequences = []
    current = [events[0]]

    for event in events[1:]:
        previous = current[-1]

        gap = float(event["time"]) - float(previous["time"])

        if gap <= MAX_GAP:
            current.append(event)
        else:
            sequences.append(current)
            current = [event]

    sequences.append(current)

    return sequences


def build_sequence(events, sequence_id):
    start = float(events[0]["time"])
    end = float(events[-1]["time"])

    # Evento con mayor score
    main_event = max(events, key=lambda x: float(x["score"]))

    return {
        "id": sequence_id,
        "start": round(start, 3),
        "end": round(end, 3),
        "duration": round(end - start, 3),
        "main_event": main_event["event"],
        "main_score": round(float(main_event["score"]), 4),
        "events": [
            {
                "time": round(float(event["time"]), 3),
                "event": event["event"],
                "team_side": event.get("team_side"),
                "score": round(float(event["score"]), 4),
            }
            for event in events
        ],
    }


# ========================================
# MAIN
# ========================================

print("=" * 50)
print("AGRUPANDO EVENTOS EN SECUENCIAS")
print("=" * 50)

if not EVENTS_FILE.exists():
    raise FileNotFoundError(
        f"No se encontrÃ³:\n{EVENTS_FILE}"
    )

with open(EVENTS_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

events = data["events"]

print(f"Eventos originales: {len(events)}")
print(f"MÃ¡ximo entre eventos: {MAX_GAP}s")

groups = group_events(events)

sequences = [
    build_sequence(group, index + 1)
    for index, group in enumerate(groups)
]

output = {
    "video": data.get("video", VIDEO_NAME),
    "duration": data.get("duration"),
    "total_events": len(events),
    "total_sequences": len(sequences),
    "max_gap": MAX_GAP,
    "sequences": sequences,
}

with open(SEQUENCES_FILE, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)


# ========================================
# RESULTADO
# ========================================

print()
print("=" * 50)
print("SECUENCIAS")
print("=" * 50)

for sequence in sequences:
    print(
        f"#{sequence['id']} "
        f"{sequence['start']:.3f}s â†’ "
        f"{sequence['end']:.3f}s "
        f"({sequence['duration']:.3f}s)"
    )

    print(
        f"   Principal: "
        f"{sequence['main_event']} "
        f"({sequence['main_score']:.4f})"
    )

    print(
        "   Eventos: "
        + " â†’ ".join(
            event["event"]
            for event in sequence["events"]
        )
    )

print()
print(f"Eventos originales : {len(events)}")
print(f"Secuencias         : {len(sequences)}")
print(f"Guardado en        : {SEQUENCES_FILE.resolve()}")

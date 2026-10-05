# SPOT Clips

Aplicacion de escritorio para analizar videos de futbol y generar clips automaticos de jugadas detectadas por una red neuronal de action spotting.

El flujo esta pensado para carpetas de partidos: seleccionas una o varias carpetas, la app busca videos directos dentro de cada carpeta, detecta eventos, consolida resultados, agrupa secuencias y genera clips MP4 listos para revisar.

## Que hace

- Analiza videos de partidos de futbol.
- Detecta eventos/candidatos con un modelo de SoccerNet Team Spotting.
- Guarda resultados por video en `Resultados/<nombre_del_video>/`.
- Genera clips por partido en la carpeta `Clips/`.
- Reutiliza resultados parciales si el analisis se interrumpe.
- Evita generar clips incompletos usando archivos temporales `.part.mp4`.
- Reduce la salida a maximo 1080p para que los clips pesen menos.
- Incluye una GUI en PySide6 para seleccionar carpetas, ver progreso y cancelar procesos.

## Estructura esperada

Ejemplo:

```text
D:\Videos fut\
  Ida Atlante semifinal\
    DJI_20260829162115_0088_D.MP4
    DJI_20260829172534_0089_D.MP4
```

La app genera:

```text
D:\Videos fut\
  Ida Atlante semifinal\
    Resultados\
      DJI_20260829162115_0088_D\
        events_raw.json
        events.json
        sequences.json
    Clips\
      DJI_..._SEQ01_...mp4
```

## Pipeline

1. `video_processor.py`
   - Lee el video.
   - Ejecuta el modelo neuronal.
   - Guarda `events_raw.json`.
   - Guarda avances parciales para recuperar trabajo si algo falla.

2. `consolidate_events.py`
   - Limpia y consolida eventos candidatos.
   - Genera `events.json`.

3. `group_sequences.py`
   - Agrupa eventos cercanos en secuencias.
   - Genera `sequences.json`.

4. `generate_clips.py`
   - Genera clips MP4 con FFmpeg/NVENC.
   - Une secuencias muy cercanas.
   - Evita sobrescribir clips ya existentes.
   - Detiene la generacion si no hay espacio suficiente en disco.

## Configuracion de clips

La configuracion actual esta en `generate_clips.py`:

```python
CONTEXT_BEFORE = 3
CONTEXT_AFTER = 3
MERGE_CLIP_GAP = 3
OUTPUT_MAX_WIDTH = 1920
OUTPUT_CQ = 28
```

Esto significa:

- 3 segundos antes de cada jugada.
- 3 segundos despues de cada jugada.
- fusiona jugadas separadas por huecos muy cortos.
- exporta a maximo 1080p.
- usa compresion NVENC con CQ 28.

## Requisitos

- Windows.
- Python 3.12 recomendado.
- GPU NVIDIA compatible con CUDA/NVENC.
- FFmpeg disponible en PATH.
- Dependencias de `requirements.txt`.
- Checkpoint en `checkpoints/checkpoint_best.pt`.

Instalacion para desarrollo:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Ejecutar desde codigo:

```powershell
.\.venv\Scripts\python.exe gui.py
```

## Crear ejecutable

El proyecto incluye `build_exe.ps1`.

```powershell
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

El ejecutable se genera en:

```text
dist\SPOT Clips\SPOT Clips.exe
```

Importante: no se debe mover solo el `.exe`; se debe conservar completa la carpeta `dist\SPOT Clips\`, porque ahi quedan las librerias de PySide6, Torch y CUDA.

## Sobre el ejecutable precompilado

El build local completo pesa varios GB porque incluye PyTorch y librerias CUDA. Por eso no es buena idea subir `dist/` directamente al repositorio Git normal.

Para distribuirlo conviene usar una de estas opciones:

- GitHub Releases, subiendo un `.zip` del directorio `dist\SPOT Clips`.
- Google Drive/OneDrive si se quiere compartir rapidamente.
- Un instalador externo si se quiere distribuir como aplicacion final.

## Creditos

Este proyecto adapta el modelo y parte de la arquitectura del repositorio:

- SoccerNet Team Spotting: https://github.com/SoccerNet/sn-teamspotting
- SoccerNet: https://www.soccer-net.org/

La red neuronal, la arquitectura base y el checkpoint usado provienen del trabajo de SoccerNet Team Action Spotting. Este proyecto agrega una capa practica de uso local: interfaz grafica, procesamiento por carpetas, recuperacion parcial, generacion de clips y empaquetado para Windows.

## Licencia

El repositorio base `SoccerNet/sn-teamspotting` esta publicado bajo GNU GPL v3.0. Por compatibilidad, esta adaptacion conserva esa licencia. Revisa `LICENSE`.

## Estado

Version practica/local para uso personal y pruebas con partidos grabados. Todavia puede mejorar en instalador, reduccion del build y controles visuales de sensibilidad.

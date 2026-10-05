import ctypes
import json
import os
import runpy
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QLockFile, QThread, Signal, Slot, Qt
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".m4v"}

PIPELINE_STEPS = [
    ("video_processor.py", "Detectando eventos"),
    ("consolidate_events.py", "Consolidando eventos"),
    ("group_sequences.py", "Agrupando secuencias"),
    ("generate_clips.py", "Generando clips"),
]

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def resource_dir():
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS).resolve()

    return Path(__file__).resolve().parent


@dataclass(frozen=True)
class VideoJob:
    partido_path: Path
    partido_index: int
    partido_total: int
    video_path: Path
    video_index: int
    video_total: int
    global_index: int
    global_total: int


class SleepGuard:
    def __init__(self, log):
        self.log = log

    def __enter__(self):
        if sys.platform == "win32":
            ctypes.windll.kernel32.SetThreadExecutionState(
                ES_CONTINUOUS | ES_SYSTEM_REQUIRED
            )
            self.log("Prevencion de suspension de Windows: ACTIVADA")
        return self

    def __exit__(self, exc_type, exc, traceback):
        if sys.platform == "win32":
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
            self.log("Prevencion de suspension de Windows: DESACTIVADA")


class ProcessingWorker(QObject):
    log = Signal(str)
    status = Signal(str)
    progress = Signal(int)
    video_started = Signal(str, int, int)
    finished = Signal(dict)

    def __init__(self, jobs, app_dir):
        super().__init__()
        self.jobs = jobs
        self.app_dir = Path(app_dir).resolve()
        self.cancel_requested = False
        self.current_process = None

    @Slot()
    def request_cancel(self):
        self.cancel_requested = True
        self.log.emit("Cancelando...")
        self.stop_current_process()

    @Slot()
    def run(self):
        summary = {
            "partidos": len({job.partido_path for job in self.jobs}),
            "selected": len(self.jobs),
            "completed": 0,
            "failed": [],
            "cancelled": False,
        }

        with SleepGuard(self.log.emit):
            for job in self.jobs:
                if self.cancel_requested:
                    break

                ok = self.process_job(job)
                if ok:
                    summary["completed"] += 1
                elif self.cancel_requested:
                    break
                else:
                    summary["failed"].append(str(job.video_path))

            summary["cancelled"] = self.cancel_requested

        self.current_process = None
        self.finished.emit(summary)

    def process_job(self, job):
        self.video_started.emit(
            job.video_path.name,
            job.global_index,
            job.global_total,
        )
        self.progress.emit(self.completed_video_progress(job.global_index, job.global_total))

        self.log.emit("")
        self.log.emit("=" * 70)
        self.log.emit(f"PARTIDO {job.partido_index}/{job.partido_total}")
        self.log.emit(str(job.partido_path))
        self.log.emit(f"VIDEO {job.video_index}/{job.video_total}")
        self.log.emit(job.video_path.name)
        self.log.emit("=" * 70)

        start_step = 1

        if self.has_usable_raw_events(job.video_path):
            self.log.emit("")
            self.log.emit(
                "events_raw.json existente detectado; se reutilizara para generar clips."
            )
            start_step = 2

        for step_index, (script_name, stage_name) in enumerate(PIPELINE_STEPS, start=1):
            if step_index < start_step:
                continue

            if self.cancel_requested:
                return False

            self.status.emit(
                f"Partido {job.partido_index}/{job.partido_total} | "
                f"Video {job.global_index}/{job.global_total} | "
                f"Etapa: {stage_name}"
            )
            self.log.emit("")
            self.log.emit("-" * 70)
            self.log.emit(f"Ejecutando {script_name}...")
            self.log.emit(f"Etapa: {stage_name}")
            self.log.emit("-" * 70)

            return_code = self.run_step(job, script_name, step_index)
            if self.cancel_requested:
                return False

            if return_code != 0:
                if step_index == 1 and self.has_usable_raw_events(job.video_path):
                    self.log.emit(
                        "video_processor.py fallo, pero dejo events_raw.json usable."
                    )
                    self.log.emit(
                        "Continuando automaticamente con consolidacion, secuencias y clips parciales..."
                    )
                    continue

                self.log.emit(
                    f"ERROR: {script_name} termino con codigo {return_code}."
                )
                self.log.emit("Continuando con el siguiente video...")
                return False

        self.log.emit("")
        self.log.emit(f"VIDEO TERMINADO: {job.video_path.name}")
        self.progress.emit(int(job.global_index / job.global_total * 100))
        return True

    def raw_events_file(self, video_path):
        return (
            video_path.parent
            / "Resultados"
            / video_path.stem
            / "events_raw.json"
        )

    def has_usable_raw_events(self, video_path):
        events_file = self.raw_events_file(video_path)
        if not events_file.exists():
            return False

        try:
            with open(events_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            self.log.emit(f"events_raw.json no se pudo leer: {exc}")
            return False

        events = data.get("events", [])
        if not events:
            self.log.emit(
                f"events_raw.json existe pero no tiene eventos: {events_file}"
            )
            return False

        state = data.get("processing_state", {})
        if state.get("partial"):
            self.log.emit(
                f"Usando detecciones parciales: {len(events)} eventos, "
                f"{state.get('processed_windows', '?')} ventanas."
            )
        else:
            self.log.emit(f"Usando detecciones existentes: {len(events)} eventos.")

        return True

    def run_step(self, job, script_name, step_index):
        command = self.build_command(script_name, job.video_path)
        startupinfo = None
        creationflags = 0
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        try:
            self.current_process = subprocess.Popen(
                command,
                cwd=str(self.app_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creationflags,
                startupinfo=startupinfo,
                env=env,
            )

            stdout = self.current_process.stdout
            if stdout is not None:
                for line in iter(stdout.readline, ""):
                    if self.cancel_requested:
                        self.stop_current_process()
                        break

                    text = line.rstrip()
                    if text:
                        self.log.emit(text)
                        self.emit_step_progress(job, step_index, text)

            return self.current_process.wait()

        except Exception as exc:
            self.log.emit(f"ERROR ejecutando {script_name}: {exc}")
            return 1

        finally:
            self.current_process = None

    def build_command(self, script_name, video_path):
        script_path = self.app_dir / script_name
        if getattr(sys, "frozen", False):
            return [
                sys.executable,
                "--spot-worker",
                script_name,
                str(video_path),
            ]

        return [
            sys.executable,
            "-u",
            str(script_path),
            str(video_path),
        ]

    def stop_current_process(self):
        process = self.current_process
        if process is None or process.poll() is not None:
            return

        try:
            if sys.platform == "win32":
                subprocess.run(
                    [
                        "taskkill",
                        "/PID",
                        str(process.pid),
                        "/T",
                        "/F",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
        except Exception as exc:
            self.log.emit(f"Advertencia al cancelar proceso: {exc}")

    def emit_step_progress(self, job, step_index, line):
        step_count = len(PIPELINE_STEPS)
        base_steps_done = (job.global_index - 1) * step_count + (step_index - 1)
        total_steps = job.global_total * step_count
        step_fraction = 0.0

        if step_index == 1 and line.startswith("Ventana "):
            step_fraction = 0.35
        elif step_index > 1:
            step_fraction = 0.5

        value = int((base_steps_done + step_fraction) / total_steps * 100)
        self.progress.emit(max(0, min(99, value)))

    @staticmethod
    def completed_video_progress(global_index, global_total):
        if global_index <= 1:
            return 0
        return int((global_index - 1) / global_total * 100)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.app_dir = resource_dir()
        self.partidos = {}
        self.thread = None
        self.worker = None
        self.closing_after_cancel = False

        self.setWindowTitle("SPOT - Soccer Analyzer")
        self.resize(1150, 800)
        self.setMinimumSize(950, 650)
        self.build_ui()

    def build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("SPOT - Soccer Analyzer")
        title.setStyleSheet("font-size: 28px; font-weight: bold;")
        subtitle = QLabel("Selecciona uno o varios partidos y los videos que quieras procesar.")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        splitter = QSplitter(Qt.Horizontal)

        partidos_group = QGroupBox("Partidos")
        partidos_layout = QVBoxLayout(partidos_group)
        self.partidos_list = QListWidget()
        self.partidos_list.currentItemChanged.connect(self.on_partido_selected)
        partidos_layout.addWidget(self.partidos_list)

        buttons = QHBoxLayout()
        self.add_button = QPushButton("+ Agregar carpeta")
        self.add_button.clicked.connect(self.add_partido)
        self.remove_button = QPushButton("Quitar")
        self.remove_button.clicked.connect(self.remove_partido)
        self.clear_button = QPushButton("Limpiar")
        self.clear_button.clicked.connect(self.clear_partidos)
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.remove_button)
        buttons.addWidget(self.clear_button)
        partidos_layout.addLayout(buttons)
        splitter.addWidget(partidos_group)

        videos_group = QGroupBox("Videos del partido")
        videos_layout = QVBoxLayout(videos_group)
        self.selected_partido_label = QLabel("Selecciona un partido")
        self.selected_partido_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.video_count_label = QLabel("0 videos")
        videos_layout.addWidget(self.selected_partido_label)
        videos_layout.addWidget(self.video_count_label)

        self.videos_list = QListWidget()
        self.videos_list.itemChanged.connect(self.on_video_changed)
        videos_layout.addWidget(self.videos_list)

        select_buttons = QHBoxLayout()
        self.select_all_button = QPushButton("Seleccionar todos")
        self.select_all_button.clicked.connect(self.select_all_videos)
        self.deselect_button = QPushButton("Deseleccionar todos")
        self.deselect_button.clicked.connect(self.deselect_all_videos)
        select_buttons.addWidget(self.select_all_button)
        select_buttons.addWidget(self.deselect_button)
        videos_layout.addLayout(select_buttons)
        splitter.addWidget(videos_group)
        splitter.setSizes([400, 750])
        layout.addWidget(splitter, 1)

        self.status_label = QLabel("Agrega una carpeta para comenzar.")
        self.status_label.setStyleSheet("padding: 8px;")
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("Los mensajes del procesamiento apareceran aqui.")
        self.log_view.setMinimumHeight(180)
        layout.addWidget(self.log_view)

        action_buttons = QHBoxLayout()
        self.process_button = QPushButton("PROCESAR")
        self.process_button.setMinimumHeight(50)
        self.process_button.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.process_button.clicked.connect(self.process_clicked)
        action_buttons.addWidget(self.process_button)

        self.cancel_button = QPushButton("CANCELAR")
        self.cancel_button.setMinimumHeight(50)
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_processing)
        action_buttons.addWidget(self.cancel_button)
        layout.addLayout(action_buttons)

    @staticmethod
    def find_videos(path):
        return sorted(
            p
            for p in path.iterdir()
            if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
        )

    def add_partido(self):
        if self.worker is not None:
            return

        folder = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta del partido")
        if not folder:
            return

        path = Path(folder).resolve()
        key = str(path)
        if key in self.partidos:
            QMessageBox.information(
                self,
                "Carpeta ya agregada",
                "Esta carpeta ya esta en la lista.",
            )
            return

        videos = self.find_videos(path)
        self.partidos[key] = {
            "path": path,
            "videos": videos,
            "selected": set(videos),
        }

        item = QListWidgetItem(f"{path.name}  ({len(videos)} videos)")
        item.setData(Qt.UserRole, key)
        self.partidos_list.addItem(item)
        self.partidos_list.setCurrentItem(item)
        self.status_label.setText(
            f"Agregado: {path.name} - {len(videos)} videos encontrados."
        )

    def remove_partido(self):
        item = self.partidos_list.currentItem()
        if item is None or self.worker is not None:
            return
        key = item.data(Qt.UserRole)
        self.partidos.pop(key, None)
        self.partidos_list.takeItem(self.partidos_list.row(item))
        self.refresh_empty_selection()
        self.status_label.setText("Partido eliminado.")

    def clear_partidos(self):
        if self.worker is not None:
            return
        self.partidos.clear()
        self.partidos_list.clear()
        self.refresh_empty_selection()
        self.status_label.setText("Lista de partidos limpiada.")

    def refresh_empty_selection(self):
        self.videos_list.clear()
        self.selected_partido_label.setText("Selecciona un partido")
        self.video_count_label.setText("0 videos")

    def on_partido_selected(self, current, previous):
        if current is None:
            self.refresh_empty_selection()
            return
        partido = self.partidos.get(current.data(Qt.UserRole))
        if partido:
            self.refresh_videos(partido)

    def refresh_videos(self, partido):
        self.videos_list.blockSignals(True)
        self.videos_list.clear()
        self.selected_partido_label.setText(partido["path"].name)
        self.video_count_label.setText(
            f'{len(partido["videos"])} videos - {len(partido["selected"])} seleccionados'
        )

        for video in partido["videos"]:
            item = QListWidgetItem(video.name)
            item.setData(Qt.UserRole, str(video))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if video in partido["selected"] else Qt.Unchecked)
            self.videos_list.addItem(item)

        self.videos_list.blockSignals(False)

    def on_video_changed(self, item):
        current = self.partidos_list.currentItem()
        if current is None:
            return
        partido = self.partidos.get(current.data(Qt.UserRole))
        if partido is None:
            return

        video = Path(item.data(Qt.UserRole))
        if item.checkState() == Qt.Checked:
            partido["selected"].add(video)
        else:
            partido["selected"].discard(video)

        self.video_count_label.setText(
            f'{len(partido["videos"])} videos - {len(partido["selected"])} seleccionados'
        )

    def select_all_videos(self):
        current = self.partidos_list.currentItem()
        if current is None or self.worker is not None:
            return
        partido = self.partidos.get(current.data(Qt.UserRole))
        if partido:
            partido["selected"] = set(partido["videos"])
            self.refresh_videos(partido)

    def deselect_all_videos(self):
        current = self.partidos_list.currentItem()
        if current is None or self.worker is not None:
            return
        partido = self.partidos.get(current.data(Qt.UserRole))
        if partido:
            partido["selected"].clear()
            self.refresh_videos(partido)

    def build_jobs(self):
        selected_by_partido = []
        for partido in self.partidos.values():
            selected = [
                video for video in partido["videos"]
                if video in partido["selected"]
            ]
            if selected:
                selected_by_partido.append((partido["path"], selected))

        global_total = sum(len(videos) for _, videos in selected_by_partido)
        partido_total = len(selected_by_partido)
        jobs = []
        global_index = 1

        for partido_index, (partido_path, videos) in enumerate(selected_by_partido, start=1):
            video_total = len(videos)
            for video_index, video_path in enumerate(videos, start=1):
                jobs.append(
                    VideoJob(
                        partido_path=partido_path,
                        partido_index=partido_index,
                        partido_total=partido_total,
                        video_path=video_path,
                        video_index=video_index,
                        video_total=video_total,
                        global_index=global_index,
                        global_total=global_total,
                    )
                )
                global_index += 1

        return jobs

    def process_clicked(self):
        if self.worker is not None:
            return
        if not self.partidos:
            QMessageBox.warning(self, "Sin partidos", "Agrega al menos una carpeta de partido.")
            return

        jobs = self.build_jobs()
        if not jobs:
            QMessageBox.warning(self, "Sin videos", "Selecciona al menos un video para procesar.")
            return

        answer = QMessageBox.question(
            self,
            "Iniciar procesamiento",
            f"Se procesaran {len(jobs)} videos en "
            f"{len({job.partido_path for job in jobs})} partidos.\n\n"
            "Iniciar ahora?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if answer != QMessageBox.Yes:
            return

        self.start_processing(jobs)

    def start_processing(self, jobs):
        self.log_view.clear()
        self.progress_bar.setValue(0)
        self.status_label.setText(f"Preparando {len(jobs)} videos...")

        self.set_controls_enabled(False)
        self.cancel_button.setEnabled(True)

        self.thread = QThread(self)
        self.worker = ProcessingWorker(jobs, self.app_dir)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.log.connect(self.append_log)
        self.worker.status.connect(self.status_label.setText)
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.video_started.connect(self.on_video_started)
        self.worker.finished.connect(self.on_processing_finished)
        self.worker.finished.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self.clear_worker_refs)

        self.thread.start()

    def cancel_processing(self):
        if self.worker is None:
            return
        self.cancel_button.setEnabled(False)
        self.status_label.setText("Cancelando...")
        self.worker.request_cancel()

    @Slot(str)
    def append_log(self, text):
        self.log_view.append(text)
        scrollbar = self.log_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    @Slot(str, int, int)
    def on_video_started(self, video_name, index, total):
        self.status_label.setText(f"Video {index}/{total}: {video_name}")

    @Slot(dict)
    def on_processing_finished(self, summary):
        failed_count = len(summary["failed"])
        cancelled = summary["cancelled"]

        if not cancelled:
            self.progress_bar.setValue(100)

        self.cancel_button.setEnabled(False)
        self.set_controls_enabled(True)

        lines = [
            "",
            "=" * 70,
            "RESUMEN FINAL",
            "=" * 70,
            f"Partidos: {summary['partidos']}",
            f"Videos seleccionados: {summary['selected']}",
            f"Completados: {summary['completed']}",
            f"Errores: {failed_count}",
            f"Cancelados: {1 if cancelled else 0}",
        ]

        if summary["failed"]:
            lines.append("")
            lines.append("Videos con error:")
            lines.extend(f"  - {path}" for path in summary["failed"])

        for line in lines:
            self.append_log(line)

        message = "\n".join(lines[3:])
        if cancelled:
            self.status_label.setText("Procesamiento cancelado.")
            QMessageBox.information(self, "Procesamiento cancelado", message)
        elif failed_count:
            self.status_label.setText(
                f"Procesamiento terminado con errores. "
                f"Terminados: {summary['completed']}; errores: {failed_count}."
            )
            QMessageBox.warning(self, "Procesamiento terminado con errores", message)
        else:
            self.status_label.setText(
                f"Procesamiento terminado. Terminados: {summary['completed']}; errores: 0."
            )
            QMessageBox.information(self, "Procesamiento terminado", message)

        if self.closing_after_cancel:
            QApplication.instance().quit()

    def clear_worker_refs(self):
        self.worker = None
        self.thread = None

    def set_controls_enabled(self, enabled):
        self.add_button.setEnabled(enabled)
        self.remove_button.setEnabled(enabled)
        self.clear_button.setEnabled(enabled)
        self.partidos_list.setEnabled(enabled)
        self.videos_list.setEnabled(enabled)
        self.select_all_button.setEnabled(enabled)
        self.deselect_button.setEnabled(enabled)
        self.process_button.setEnabled(enabled)

    def closeEvent(self, event):
        if self.worker is not None:
            answer = QMessageBox.question(
                self,
                "Procesamiento en curso",
                "Hay un procesamiento en curso. Quieres cancelarlo y cerrar?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                event.ignore()
                return

            self.closing_after_cancel = True
            self.cancel_processing()
            event.ignore()
            return

        event.accept()


def main():
    if len(sys.argv) >= 4 and sys.argv[1] == "--spot-worker":
        script_name = sys.argv[2]
        video_path = sys.argv[3]
        script_path = resource_dir() / script_name
        sys.argv = [str(script_path), video_path]
        runpy.run_path(str(script_path), run_name="__main__")
        return

    app = QApplication(sys.argv)

    lock_base = Path(sys.executable if getattr(sys, "frozen", False) else __file__)
    lock_file = QLockFile(str(lock_base.resolve().with_suffix(".lock")))
    lock_file.setStaleLockTime(30000)
    acquired_lock = lock_file.tryLock(100)
    if not acquired_lock:
        lock_file.removeStaleLockFile()
        acquired_lock = lock_file.tryLock(100)
    if not acquired_lock:
        QMessageBox.warning(
            None,
            "SPOT ya esta abierto",
            "Ya hay una instancia de SPOT ejecutandose. Usa la ventana abierta.",
        )
        return
    app.spot_lock_file = lock_file

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

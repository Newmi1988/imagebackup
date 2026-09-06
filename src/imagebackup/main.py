# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "flask>=3.1.3",
#     "python-json-logger>=4.0.0",
# ]
# ///

import os
import shutil
import time
import threading
import json
import logging
from datetime import datetime
from flask import Flask, render_template_string, jsonify
import argparse
from pythonjsonlogger.json import JsonFormatter

# --- Pfad-Konfiguration (Standardwerte) ---
DEFAULT_SOURCE_DIR = "/media/usb0"
DEFAULT_DEST_BASE = "/media/usb1"

# --- Globale Status-Variablen ---
status_data = {
    "phase": "IDLE",
    "line1": "Warte auf Medien...",
    "line2": "SD & SSD einstecken",
    "progress": 0,
    "active": False,
    "media_ready": False,
}
stop_requested = threading.Event()
start_requested = threading.Event()


def setup_logging():
    handler = logging.StreamHandler()
    formatter = JsonFormatter(
        "{asctime} {levelname} {name} {message}",
        style="{",
        rename_fields={"asctime": "timestamp", "levelname": "level", "name": "logger"},
    )
    handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers = [handler]

    # Configure Werkzeug / Flask logging to use our handler
    werkzeug_logger = logging.getLogger("werkzeug")
    werkzeug_logger.handlers = [handler]
    werkzeug_logger.propagate = False


logger = logging.getLogger("imagebackup")

app = Flask(__name__)

# --- HTML-Oberfläche für dein Smartphone (Minimalistisch Schwarz/Weiß) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Backup Box Progress</title>
    <style>
        body { background-color: #000; color: #fff; font-family: monospace; padding: 20px; text-align: center; }
        .container { max-width: 400px; margin: auto; border: 1px solid #fff; padding: 20px; }
        h1 { border-bottom: 1px solid #fff; padding-bottom: 10px; font-size: 1.2em; }
        p { font-size: 1.1em; min-height: 20px; }
        .progress-box { border: 1px solid #fff; height: 30px; width: 100%; margin-top: 20px; position: relative; }
        .progress-bar { background-color: #fff; height: 100%; width: 0%; transition: width 0.3s; }
        .pct { position: absolute; width: 100%; text-align: center; top: 5px; color: #888; mix-blend-mode: difference; font-weight: bold; }
        .btn-group { display: flex; gap: 10px; margin-top: 25px; }
        .btn {
            flex: 1;
            padding: 12px 10px;
            background-color: #000;
            color: #fff;
            border: 1px solid #fff;
            font-family: monospace;
            font-size: 1em;
            cursor: pointer;
            text-transform: uppercase;
            box-sizing: border-box;
            transition: background-color 0.2s, color 0.2s;
        }
        .btn:hover:not(:disabled) { background-color: #fff; color: #000; }
        .btn:disabled { opacity: 0.35; cursor: not-allowed; border-color: #555; color: #777; }
    </style>
    <script>
        async function startBackup() {
            const btn = document.getElementById('start-btn');
            btn.disabled = true;
            btn.innerText = 'STARTING...';
            try {
                await fetch('/start', { method: 'POST' });
            } catch (err) {
                console.error('Start request failed', err);
            }
        }

        async function stopBackup() {
            const btn = document.getElementById('stop-btn');
            btn.disabled = true;
            btn.innerText = 'STOPPING...';
            try {
                await fetch('/stop', { method: 'POST' });
            } catch (err) {
                console.error('Stop request failed', err);
            }
        }

        setInterval(async () => {
            let res = await fetch('/status');
            let data = await res.json();
            document.getElementById('phase').innerText = data.phase;
            document.getElementById('line1').innerText = data.line1;
            document.getElementById('line2').innerText = data.line2;
            document.getElementById('bar').style.width = data.progress + '%';
            document.getElementById('pct').innerText = data.progress + '%';

            const startBtn = document.getElementById('start-btn');
            const stopBtn = document.getElementById('stop-btn');

            startBtn.disabled = data.active || !data.media_ready;
            if (data.active) {
                startBtn.innerText = 'START BACKUP';
            }

            stopBtn.disabled = !data.active;
            if (!data.active) {
                stopBtn.innerText = 'STOP BACKUP';
            }
        }, 1000);
    </script>
</head>
<body>
    <div class="container">
        <h1 id="phase">WAITING</h1>
        <p id="line1">Lade...</p>
        <p id="line2">...</p>
        <div class="progress-box">
            <div id="bar" class="progress-bar"></div>
            <div id="pct" class="pct">0%</div>
        </div>
        <div class="btn-group">
            <button id="start-btn" class="btn" onclick="startBackup()" disabled>START BACKUP</button>
            <button id="stop-btn" class="btn" onclick="stopBackup()" disabled>STOP BACKUP</button>
        </div>
    </div>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route('/status')
def get_status():
    return jsonify(status_data)

@app.route('/start', methods=['POST'])
def start():
    if status_data.get("active"):
        return jsonify({"success": False, "message": "Backup is already running"}), 400
    if not status_data.get("media_ready"):
        return jsonify({"success": False, "message": "Media not ready"}), 400
    start_requested.set()
    logger.info("Start requested via UI")
    return jsonify({"success": True, "message": "Start requested"})

@app.route('/stop', methods=['POST'])
def stop():
    if status_data.get("active"):
        stop_requested.set()
        logger.info("Stop requested via UI")
        return jsonify({"success": True, "message": "Stop requested"})
    return jsonify({"success": False, "message": "No active backup running"}), 400

def get_transfer_list(source_dir):
    file_list = []
    total_size = 0
    for root, _, files in os.walk(source_dir):
        for file in files:
            if file.lower().endswith(('.jpg', '.jpeg', '.cr2', '.nef', '.arw', '.dng')):
                full_path = os.path.join(root, file)
                try:
                    file_list.append((full_path, root, file))
                    total_size += os.path.getsize(full_path)
                except OSError:
                    continue
    return file_list, total_size

def backup_worker(source_dir, dest_base):
    """Der eigentliche Backup-Prozess läuft in einem eigenen Thread."""
    global status_data
    media_previously_connected = False

    while True:
        media_present = (
            os.path.exists(source_dir)
            and os.path.exists(dest_base)
            and len(os.listdir(source_dir)) > 0
        )
        status_data["media_ready"] = media_present

        # Auto-trigger when media is newly connected OR triggered via UI button
        should_run = (media_present and not media_previously_connected) or (media_present and start_requested.is_set())

        if should_run:
            start_requested.clear()
            stop_requested.clear()
            media_previously_connected = True

            status_data.update({"phase": "SYSTEM SCAN", "line1": "Analysiere Daten...", "line2": "Bitte warten...", "progress": 0, "active": True})
            time.sleep(2)
            
            files_to_copy, total_size = get_transfer_list(source_dir)
            if not files_to_copy:
                status_data.update({"phase": "ABBRUCH", "line1": "Keine kompatiblen Fotos", "line2": "auf SD-Karte gefunden.", "progress": 0, "active": False})
                time.sleep(5)
                continue

            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            target_folder = os.path.join(dest_base, f"Backup_{timestamp}")
            os.makedirs(target_folder, exist_ok=True)
            log_file_path = os.path.join(target_folder, "backup_log.jsonl")
            
            copied_size = 0
            total_files = len(files_to_copy)
            copy_errors = 0
            verification_errors = 0
            copied_records = []
            aborted = False
            
            # 1. Kopier-Schleife (0% - 50%)
            for index, (src_file, root, file) in enumerate(files_to_copy):
                if stop_requested.is_set():
                    aborted = True
                    logger.info("Backup process stopped by user during copy phase")
                    break

                rel_path = os.path.relpath(root, source_dir)
                dest_dir = os.path.join(target_folder, rel_path)
                os.makedirs(dest_dir, exist_ok=True)
                dest_file = os.path.join(dest_dir, file)
                
                try: file_size = os.path.getsize(src_file)
                except OSError: continue
                    
                progress_pct = int((copied_size / total_size) * 50) if total_size > 0 else 0
                short_name = file if len(file) < 22 else file[:19] + "..."
                status_data.update({"phase": "1/2 KOPIEREN", "line1": f"Datei: {index+1}/{total_files}", "line2": short_name, "progress": progress_pct, "active": True})
                
                try:
                    shutil.copy2(src_file, dest_dir)
                    copied_size += file_size
                    copied_records.append((src_file, dest_file, file_size))
                except Exception as e:
                    copy_errors += 1
                    err_event = {
                        "timestamp": datetime.now().isoformat(),
                        "event": "copy_failed",
                        "source": src_file,
                        "error": str(e),
                    }
                    logger.error("Copy failed: %s | %s", src_file, e)
                    with open(log_file_path, "a") as log:
                        log.write(json.dumps(err_event) + "\n")

            # 2. Verifizierungs-Schleife (50% - 100%)
            if not aborted:
                status_data.update({"phase": "2/2 VERIFIZIERUNG", "line1": "Starte Datenabgleich...", "line2": "Bitte warten...", "progress": 50, "active": True})
                time.sleep(1)
                
                for index, (src, dest, expected_size) in enumerate(copied_records):
                    if stop_requested.is_set():
                        aborted = True
                        logger.info("Backup process stopped by user during verification phase")
                        break

                    progress_pct = 50 + int((index / len(copied_records)) * 50) if copied_records else 100
                    short_name = os.path.basename(src)
                    short_name = short_name if len(short_name) < 22 else short_name[:19] + "..."
                    status_data.update({"phase": "2/2 VERIFIZIERUNG", "line1": f"Prüfung: {index+1}/{len(copied_records)}", "line2": short_name, "progress": progress_pct, "active": True})
                    
                    try:
                        if not os.path.exists(dest) or os.path.getsize(dest) != expected_size:
                            raise ValueError("Größenfehler")
                    except Exception as e:
                        verification_errors += 1
                        err_event = {
                            "timestamp": datetime.now().isoformat(),
                            "event": "verify_failed",
                            "dest": dest,
                            "error": str(e),
                        }
                        logger.error("Verify failed: %s | %s", dest, e)
                        with open(log_file_path, "a") as log:
                            log.write(json.dumps(err_event) + "\n")

            # Fertig / Gestoppt
            if aborted:
                status_data.update({"phase": "GESTOPPT", "line1": "Backup abgebrochen", "line2": "Vorgang durch Benutzer beendet.", "progress": status_data.get("progress", 0), "active": False})
            else:
                total_issues = copy_errors + verification_errors
                if total_issues > 0:
                    status_data.update({"phase": "WARNUNG", "line1": f"Fehler aufgetreten: {total_issues}", "line2": "Logdatei auf SSD prüfen!", "progress": 100, "active": False})
                else:
                    status_data.update({"phase": "ERFOLG", "line1": "100% Erfolgreich Verifiziert", "line2": "Speicher sicher trennen.", "progress": 100, "active": False})

        elif not media_present:
            media_previously_connected = False
            start_requested.clear()
            status_data.update({"phase": "READY TO BACKUP", "line1": "Warte auf Medien...", "line2": "SD & SSD einstecken.", "progress": 0, "active": False})

        time.sleep(1)

def parse_args():
    parser = argparse.ArgumentParser(description="Image Backup Service")
    parser.add_argument(
        "--source",
        "-s",
        default=DEFAULT_SOURCE_DIR,
        help=f"Source directory containing photos (default: {DEFAULT_SOURCE_DIR})",
    )
    parser.add_argument(
        "--dest",
        "-d",
        default=DEFAULT_DEST_BASE,
        help=f"Destination directory for backups (default: {DEFAULT_DEST_BASE})",
    )
    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=8000,
        help="Port to run the web server on (default: 5000)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host IP to bind the web server to (default: 0.0.0.0)",
    )
    return parser.parse_args()


def main():
    setup_logging()
    args = parse_args()

    # Startet den Backup-Überwacher in einem eigenen Thread im Hintergrund
    threading.Thread(target=backup_worker, args=(args.source, args.dest), daemon=True).start()
    # Startet den Webserver, erreichbar im ganzen Netzwerk
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()


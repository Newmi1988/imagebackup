# 📸 Mobile Photo Backup Box (Raspberry Pi 5)

A completely automated, screenless field-backup system that copies RAW and JPEG image files from an SD card onto an external USB-C SSD. Optimized for on-the-go field use, this system requires no internet connection and turns your smartphone into a wireless live display to monitor backup status and progress.

---

## 🛠️ System Architecture & Hardware

The system is powered in the field by a high-output power bank and utilizes the fast USB 3.0 buses of the Raspberry Pi 5 to ensure maximum transfer speeds for large datasets (200 GB+).

### 📋 Bill of Materials (BOM)

* **Central Unit (Brain):** Raspberry Pi 5 (4GB RAM)
* **Operating System Storage:** 16GB or 32GB MicroSD card
* **Power Supply:** Anker 737 Power Bank (PowerCore 24K) with Trickle-Charging Mode enabled
* **Power Cable:** High-quality USB-C to USB-C cable (Power Delivery rated)
* **Source Drive:** Your existing USB 3.0 SD card reader
* **Target Drive:** Your existing external USB-C SSD
* **Enclosure:** Standard protective case for the Raspberry Pi 5

### 🔌 Connection Diagram

```text
+--------------------------------------------------------+
|                    PORTABLE CAMERA BAG                 |
|                                                        |
|  [ Anker 737 Power Bank ]                              |
|        |                                               |
|        +---> (USB-C PD Cable) ---> [ Pi Power Port ]   |
|                                                        |
|  [ Raspberry Pi 5 (4GB) ]                              |
|        |                                               |
|        +---> [ Blue USB 3.0 Port A ] ---> [ SSD ]      |
|        +---> [ Blue USB 3.0 Port B ] ---> [ SD Reader] |
|                                                        |
|  [ Built-in Wi-Fi ] - - - - (Hotspot) - - - [ Phone ]  |
+--------------------------------------------------------+
```

---

## ⚙️ Field Operations (Workflow)

1. **Power On:** Connect the Raspberry Pi to the Anker 737. Double-click the power bank's side button to activate its low-current "Trickle-Charging" mode so it never sleeps.
2. **Connect Phone:** Open your smartphone's Wi-Fi settings and connect to the network named `Photo-Backup-Box`.
3. **Open the Dashboard:** Open Safari or Chrome on your phone and navigate to `http://192.168.4.1:5000` (or configured port). The high-contrast black-and-white web UI will display `READY TO BACKUP`.
4. **Trigger Backup:**
   - **Automatic:** Plug in your SD card reader and USB-C SSD. The system auto-detects the connected drives and immediately begins the backup.
   - **Manual:** Use the **START BACKUP** button on the web dashboard to trigger or retry a backup without re-inserting media.
5. **Control in Progress:** You can tap the **STOP BACKUP** button at any time during copying or verification to abort safely.
6. **Safe to Disconnect:** After copying, a bit-accurate file size verification pass runs. When the screen updates to `100% Successfully Verified`, it is safe to unplug your media. If errors occur, a structured JSONL log file (`backup_log.jsonl`) is created inside the backup folder on your SSD.

---

## 🚀 Installation & Running

The application can be installed and run directly from GitHub using [`uvx`](https://docs.astral.sh/uv/guides/tools/) (bundled with `uv`) without needing to manually clone the repository:

### Run directly with `uvx` (No installation needed)
```bash
uvx --from git+https://github.com/Newmi1988/imagebackup.git imagebackup
```

You can pass arguments directly:
```bash
uvx --from git+https://github.com/Newmi1988/imagebackup.git imagebackup --port 8080
```

### Install as a global tool with `uv tool install`
```bash
uv tool install git+https://github.com/Newmi1988/imagebackup.git
```
Once installed, execute it anytime simply as:
```bash
imagebackup --source /media/usb0 --dest /media/usb1
```
To update to the latest commit on `main`:
```bash
uv tool upgrade imagebackup
```

### For Local Development
If you have cloned the repository locally:
```bash
# Run project CLI
uv run imagebackup

# Or run the script directly
uv run src/imagebackup/main.py
```

Run the unit tests with pytest:
```bash
uv run --group dev pytest
```

### Command-Line Arguments
```text
usage: imagebackup [-h] [--source SOURCE] [--dest DEST] [--port PORT] [--host HOST]

optional arguments:
  -h, --help            show this help message and exit
  --source SOURCE, -s SOURCE
                        Source directory containing photos (default: /media/usb0)
  --dest DEST, -d DEST  Destination directory for backups (default: /media/usb1)
  --port PORT, -p PORT  Port to run the web server on (default: 5000)
  --host HOST           Host IP to bind the web server to (default: 0.0.0.0)
```

**Example:**
```bash
uv run imagebackup --source /Volumes/SD_CARD --dest /Volumes/BACKUP_SSD --port 8080
```

---

## 📝 Logging Format

The server outputs JSON logs via `python-json-logger` for both console output and file errors:

- **Application Logs (stdout):**
  ```json
  {"timestamp": "2026-09-06 19:35:01,602", "level": "INFO", "logger": "imagebackup", "message": "Start requested via UI"}
  ```
- **Backup Error Log (`backup_log.jsonl`):**
  Written directly into the specific `Backup_<timestamp>` folder whenever file copy or verification errors occur:
  ```json
  {"timestamp": "2026-09-06T19:30:00.123456", "event": "copy_failed", "source": "/media/usb0/DCIM/IMG_0001.CR2", "error": "[Errno 5] Input/output error"}
  ```

---

## 💻 Software Installation & Configuration (Raspberry Pi)

### 1. Install Dependencies & uv

```bash
sudo apt update
sudo apt install usbmount -y
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Install `imagebackup` directly from GitHub into user tools:
```bash
uv tool install git+https://github.com/Newmi1988/imagebackup.git
```

### 2. Configure Write Permissions for exFAT/NTFS Drives
Open the USB automount configuration file:
```bash
sudo nano /etc/usbmount/usbmount.conf
```
Ensure exFAT/NTFS mount options allow writing:
```bash
FILESYSTEMS="vfat ext4 hfsplus ntfs exfat"
FS_MOUNTOPTIONS="-fstype=vfat,gid=pi,uid=pi,dmask=0022,fmask=0111 -fstype=exfat,uid=1000,gid=1000,umask=007"
```

### 3. Establish the Wi-Fi Hotspot
Create the local wireless network profile using NetworkManager:
```bash
sudo nmcli device wifi hotspot ssid "Photo-Backup-Box" password "your_password_123"
```

### 4. Enable Script on Startup
To launch the backup daemon and web server automatically on boot, edit `/etc/rc.local`:
```bash
sudo nano /etc/rc.local
```
Add the command above `exit 0` (using the installed `uv` tool):
```bash
su - pi -c "/home/pi/.local/bin/imagebackup" &
```

---

## 📊 Features & Advantages

* **Data Integrity:** Implements a post-transfer size validation pass before confirming a successful copy.
* **Web UI Controls:** Monitor live percentage and file progress with **START BACKUP** and **STOP BACKUP** controls from any smartphone browser.
* **Structured JSON Logging:** Native JSON logs with `python-json-logger` and per-run `.jsonl` failure reports.
* **Power Efficient:** Headless operation eliminates display power draw, keeping battery consumption minimal.
* **Universal File Handling:** Seamlessly parses common RAW photography formats (`.cr2`, `.nef`, `.arw`, `.dng`) along with standard `.jpg` / `.jpeg` files.


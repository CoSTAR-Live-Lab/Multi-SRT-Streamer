import os
import re
import signal
import subprocess
import threading
import tkinter as tk
from tkinter import messagebox, ttk

FFMPEG_PATH = r"C:\ffmpeg\bin\ffmpeg.exe"

class SRTStreamerApp:

    def __init__(self, root):
        self.root = root
        self.root.title("Multi-Camera SRT Streamer")
        self.root.geometry("900x500")
        self.root.minsize(900, 500)

        # List to track active stream dictionaries
        # Each item: {'id': int, 'proc': Popen, 'status_var': StringVar, ...}
        self.streams = []
        self.stream_counter = 0

        # UI Setup
        self._create_widgets()

        # Protocol for graceful window closing
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Initial device scan
        self.refresh_devices()

    def _create_widgets(self):
        # -------------------------------------------------------------
        # Top Frame: Configuration / Stream Builder
        # -------------------------------------------------------------
        config_frame = ttk.LabelFrame(
            self.root, text=" Configure New Stream ", padding=10
        )
        config_frame.pack(fill="x", padx=10, pady=5)

        # Device Selection
        ttk.Label(config_frame, text="Video Device:").grid(
            row=0, column=0, sticky="w", pady=2
        )
        self.device_cb = ttk.Combobox(config_frame, width=30, state="readonly")
        self.device_cb.grid(row=0, column=1, sticky="w", padx=5, pady=2)

        self.btn_refresh = ttk.Button(
            config_frame, text="Re-scan for Devices", command=self.refresh_devices
        )
        self.btn_refresh.grid(row=0, column=2, sticky="w", padx=5, pady=2)

        # Resolution & FPS
        ttk.Label(config_frame, text="Resolution:").grid(
            row=1, column=0, sticky="w", pady=2
        )
        self.res_cb = ttk.Combobox(
            config_frame,
            values=["1920x1080", "1280x720", "640x480"],
            width=15,
        )
        self.res_cb.set("1920x1080")
        self.res_cb.grid(row=1, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(config_frame, text="FPS:").grid(
            row=1, column=2, sticky="e", pady=2
        )
        self.fps_cb = ttk.Combobox(
            config_frame, values=["30", "25", "60"], width=8
        )
        self.fps_cb.set("30")
        self.fps_cb.grid(row=1, column=3, sticky="w", padx=5, pady=2)

        # Destination IP & Port
        ttk.Label(config_frame, text="SRT Host/IP:").grid(
            row=2, column=0, sticky="w", pady=2
        )
        self.host_entry = ttk.Entry(config_frame, width=20)
        self.host_entry.insert(0, "192.168.3.16")
        self.host_entry.grid(row=2, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(config_frame, text="Port:").grid(
            row=2, column=2, sticky="e", pady=2
        )
        self.port_entry = ttk.Entry(config_frame, width=8)
        self.port_entry.insert(0, "5050")
        self.port_entry.grid(row=2, column=3, sticky="w", padx=5, pady=2)

        # Mode & Latency
        ttk.Label(config_frame, text="SRT Mode:").grid(
            row=3, column=0, sticky="w", pady=2
        )
        self.mode_cb = ttk.Combobox(
            config_frame, values=["caller", "listener"], width=10, state="readonly"
        )
        self.mode_cb.set("caller")
        self.mode_cb.grid(row=3, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(config_frame, text="Latency (µs):").grid(
            row=3, column=2, sticky="e", pady=2
        )
        self.latency_entry = ttk.Entry(config_frame, width=12)
        self.latency_entry.insert(0, "500000")  # 500 ms
        self.latency_entry.grid(row=3, column=3, sticky="w", padx=5, pady=2)

        # Stream ID & Passphrase
        ttk.Label(config_frame, text="Stream ID:").grid(
            row=4, column=0, sticky="w", pady=2
        )
        self.streamid_entry = ttk.Entry(config_frame, width=30)
        self.streamid_entry.insert(0, "")
        self.streamid_entry.grid(row=4, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(config_frame, text="Passphrase:").grid(
            row=4, column=2, sticky="e", pady=2
        )
        self.passphrase_entry = ttk.Entry(config_frame, width=20, show="*")
        self.passphrase_entry.grid(row=4, column=3, sticky="w", padx=5, pady=2)

        # Add Stream Button
        self.btn_add = ttk.Button(
            config_frame, text="➕ Add Stream", command=self.add_stream_row
        )
        self.btn_add.grid(row=5, column=0, columnspan=4, pady=10)

        # -------------------------------------------------------------
        # Bottom Frame: Active Streams List
        # -------------------------------------------------------------
        list_frame = ttk.LabelFrame(
            self.root, text=" Manage Active Streams ", padding=10
        )
        list_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # Canvas & Scrollbar for dynamic list of stream controls
        self.canvas = tk.Canvas(list_frame, borderwidth=0, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(
            list_frame, orient="vertical", command=self.canvas.yview
        )
        self.scroll_content = ttk.Frame(self.canvas)

        self.scroll_content.bind(
            "<Configure>",
            lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            ),
        )
        self.canvas.create_window(
            (0, 0), window=self.scroll_content, anchor="nw"
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

    def refresh_devices(self):
        """Scans system for DirectShow video capture devices using FFmpeg."""

        def _scan():
            devices = []
            try:
                cmd = [FFMPEG_PATH, "-list_devices", "true", "-f", "dshow", "-i", "dummy"]
                # FFmpeg prints device list to stderr
                result = subprocess.run(
                    cmd,
                    stderr=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW
                    if os.name == "nt"
                    else 0,
                )

                # Parse lines matching DirectShow video input format
                for line in result.stderr.splitlines():
                    if "(video)" in line:
                        match = re.search(r'"([^"]+)"', line)
                        if match:
                            devices.append(match.group(1))

            except Exception as e:
                print(f"Error scanning devices: {e}")

            # Update Combobox UI in main thread
            self.root.after(0, self._update_device_cb, devices)

        threading.Thread(target=_scan, daemon=True).start()

    def _update_device_cb(self, devices):
        if devices:
            self.device_cb["values"] = devices
            self.device_cb.current(0)
        else:
            self.device_cb["values"] = ["No video devices found"]
            self.device_cb.current(0)

    def add_stream_row(self):
        device = self.device_cb.get()
        if not device or device == "No video devices found":
            messagebox.showerror(
                "Error", "Please select a valid video input device."
            )
            return

        host = self.host_entry.get().strip()
        port = self.port_entry.get().strip()
        if not host or not port:
            messagebox.showerror("Error", "Host IP and Port are required.")
            return

        self.stream_counter += 1
        stream_id = self.stream_counter

        # Construct SRT URL
        mode = self.mode_cb.get()
        latency = self.latency_entry.get().strip()
        stream_key = self.streamid_entry.get().strip()
        passphrase = self.passphrase_entry.get().strip()

        srt_url = f"srt://{host}:{port}?mode={mode}&pkt_size=1316"
        if latency:
            srt_url += f"&latency={latency}"
        if stream_key:
            srt_url += f"&streamid={stream_key}"
        if passphrase:
            srt_url += f"&passphrase={passphrase}"

        # Construct FFmpeg Command
        res = self.res_cb.get().strip()
        fps = self.fps_cb.get().strip()

        ffmpeg_cmd = [
            "ffmpeg",
            "-rtbufsize",
            "500M",
            "-f",
            "dshow",
            "-video_size",
            res,
            "-framerate",
            fps,
            "-i",
            f"video={device}",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-tune",
            "zerolatency",
            "-pix_fmt",
            "yuv420p",
            "-g",
            fps,
            "-f",
            "mpegts",
            srt_url,
        ]

        # UI Row Widget Creation
        row_frame = ttk.Frame(
            self.scroll_content, padding=5, relief="groove", borderwidth=1
        )
        row_frame.pack(fill="x", expand=True, pady=3)

        info_text = f"#{stream_id} | Device: {device} | Output: {host}:{port} ({res}@{fps}fps)"
        lbl_info = ttk.Label(
            row_frame, text=info_text#, font=("Consolas", 9, "bold")
        )
        lbl_info.pack(side="left", padx=5)

        status_var = tk.StringVar(value="STOPPED")
        lbl_status = ttk.Label(
            row_frame,
            textvariable=status_var,
            foreground="gray",
            font=("Consolas", 9, "bold"),
            width=12,
        )
        lbl_status.pack(side="left", padx=10)

        stream_data = {
            "id": stream_id,
            "device": device,
            "host": host,
            "port": port,
            "res": res,
            "fps": fps,
            "cmd": ffmpeg_cmd,
            "proc": None,
            "status_var": status_var,
            "row_frame": row_frame,
            "lbl_info": lbl_info,
            "btn_start": None,
            "btn_stop": None,
        }

        btn_start = ttk.Button(
            row_frame,
            text="▶ Start",
            command=lambda: self.start_stream(stream_data),
        )
        btn_start.pack(side="left", padx=2)

        btn_stop = ttk.Button(
            row_frame,
            text="⏹ Stop",
            state="disabled",
            command=lambda: self.stop_stream(stream_data),
        )
        btn_stop.pack(side="left", padx=2)

        btn_remove = ttk.Button(
            row_frame,
            text="❌ Remove",
            command=lambda: self.remove_stream_row(stream_data),
        )
        btn_remove.pack(side="right", padx=5)

        stream_data["btn_start"] = btn_start
        stream_data["btn_stop"] = btn_stop

        self.streams.append(stream_data)

    def start_stream(self, stream_data):
        if stream_data["proc"] is not None:
            return  # Already running

        try:
            # Launch process hidden in background
            proc = subprocess.Popen(
                stream_data["cmd"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW
                if os.name == "nt"
                else 0,
            )
            stream_data["proc"] = proc
            stream_data["status_var"].set("LIVE 🔴")
            stream_data["btn_start"].config(state="disabled")
            stream_data["btn_stop"].config(state="normal")

            # Watcher thread to monitor process exit
            threading.Thread(
                target=self._monitor_process,
                args=(stream_data,),
                daemon=True,
            ).start()

        except Exception as e:
            messagebox.showerror(
                "Execution Error", f"Failed to start FFmpeg:\n{e}"
            )

    def _monitor_process(self, stream_data):
        proc = stream_data["proc"]
        if proc:
            proc.wait()  # Block until process terminates
            self.root.after(0, self._on_process_ended, stream_data)

    def _on_process_ended(self, stream_data):
        stream_data["proc"] = None
        stream_data["status_var"].set("STOPPED")
        stream_data["btn_start"].config(state="normal")
        stream_data["btn_stop"].config(state="disabled")

    def stop_stream(self, stream_data):
        proc = stream_data["proc"]
        if proc and proc.poll() is None:
            try:
                # Force kill process on Windows cleanly
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                else:
                    proc.terminate()
            except Exception as e:
                print(f"Error terminating process: {e}")

    def remove_stream_row(self, stream_data):
        """Stops and removes a stream, then re-indexes remaining streams sequentially."""
        self.stop_stream(stream_data)
        stream_data["row_frame"].destroy()

        if stream_data in self.streams:
            self.streams.remove(stream_data)

        # Re-index remaining streams sequentially (1, 2, 3...)
        for new_index, s_data in enumerate(self.streams, start=1):
            s_data["id"] = new_index
            updated_info = (
                f"#{new_index} | Device: {s_data['device']} | "
                f"Output: {s_data['host']}:{s_data['port']} ({s_data['res']}@{s_data['fps']}fps)"
            )
            s_data["lbl_info"].config(text=updated_info)

        # Update counter to match total remaining streams
        self.stream_counter = len(self.streams)

    def on_closing(self):
        """Ensures all active FFmpeg instances are killed before exiting GUI."""
        for stream_data in list(self.streams):
            self.stop_stream(stream_data)
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = SRTStreamerApp(root)
    root.mainloop()
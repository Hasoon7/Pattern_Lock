import csv
import os
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
import tkinter.font as tkfont

import serial
from serial.tools import list_ports

CSV_PATH = "leaderboard.csv"

POINTS_PER_TRY_PASS = 1
WIN_BONUS = 5


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.configure(bg="#0b0f1a")

        self.arcade_font = self._pick_font("Press Start 2P", "Consolas")
        self.retro_font = self._pick_font("VT323", "Consolas")
        self.configure(bg="#121212")
        self._setup_styles()
        self.title("Pattern Lock - Leaderboard")
        self.geometry("520x520")

        self.ser = None
        self.reader_thread = None
        self.stop_reader = threading.Event()

        self.current_player = None
        self.session_points = 0
        self.game_running = False

        self._build_ui()
        self._ensure_csv_exists()
        self.refresh_leaderboard()

    def _pick_font(self, preferred: str, fallback: str = "Consolas"):
        families = set(tkfont.families(self))
        return preferred if preferred in families else fallback

    def _build_ui(self):
        pad = {"padx": 10, "pady": 8}

        # ===== Header =====
        header = tk.Frame(self, bg="#0b0f1a")
        header.pack(fill="x", padx=12, pady=(12, 6))

        title = tk.Label(
            header,
            text="PATTERN LOCK",
            bg="#0b0f1a",
            fg="#35f2ff",  # neon cyan
            font=(self.arcade_font, 20, "bold")
        )
        title.pack()

        subtitle = tk.Label(
            header,
            text="Memory Challenge • Arduino + Sound",
            bg="#0b0f1a",
            fg="#b7c7ff",
            font=(self.retro_font, 14)
        )
        subtitle.pack(pady=(4, 0))

        # ===== Now Playing =====
        now_frame = tk.Frame(self, bg="#0b0f1a")
        now_frame.pack(fill="x", padx=12, pady=(6, 10))

        self.now_playing_var = tk.StringVar(value="Now Playing: —")
        now_playing = tk.Label(
            now_frame,
            textvariable=self.now_playing_var,
            bg="#0b0f1a",
            fg="#ff3df5",  # neon pink
            font=(self.arcade_font, 12, "bold"),
            anchor = "center"
        )
        now_playing.pack(fill="x")

        serial_frame = ttk.LabelFrame(self, text="Arduino Connection")
        serial_frame.pack(fill="x", **pad)

        ttk.Label(serial_frame, text="Port:").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(serial_frame, textvariable=self.port_var, state="readonly", width=25)
        self.port_combo.grid(row=0, column=1, padx=8, pady=6)

        ttk.Button(serial_frame, text="Scan Ports", command=self.scan_ports)\
            .grid(row=0, column=2, padx=8, pady=6)

        ttk.Button(serial_frame, text="Connect", command=self.connect)\
            .grid(row=1, column=1, sticky="w", padx=8, pady=6)

        ttk.Button(serial_frame, text="Disconnect", command=self.disconnect)\
            .grid(row=1, column=1, sticky="e", padx=8, pady=6)

        self.status_var = tk.StringVar(value="Not connected")
        ttk.Label(serial_frame, textvariable=self.status_var)\
            .grid(row=2, column=0, columnspan=3, sticky="w", padx=8, pady=6)

        player_frame = ttk.LabelFrame(self, text="Player")
        player_frame.pack(fill="x", **pad)

        ttk.Label(player_frame, text="Name:").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        self.name_var = tk.StringVar()
        ttk.Entry(player_frame, textvariable=self.name_var, width=30)\
            .grid(row=0, column=1, padx=8, pady=6)

        ttk.Button(player_frame, text="Start Game", command=self.start_game)\
            .grid(row=0, column=2, padx=8, pady=6)

        self.session_var = tk.StringVar(value="Session points: 0")
        ttk.Label(player_frame, textvariable=self.session_var)\
            .grid(row=1, column=0, columnspan=3, sticky="w", padx=8, pady=6)

        board_frame = ttk.LabelFrame(self, text="Leaderboard (CSV)")
        board_frame.pack(fill="both", expand=True, **pad)

        ttk.Button(board_frame, text="Refresh", command=self.refresh_leaderboard)\
            .pack(anchor="ne", padx=8, pady=6)

        self.tree = ttk.Treeview(
            board_frame,
            columns=("rank", "name", "score"),
            show="headings",
            style="Arcade.Treeview",
            height=14
        )
        self.tree.heading("rank", text="Rank")
        self.tree.heading("name", text="Name")
        self.tree.heading("score", text="Score")

        self.tree.column("rank", width=70, anchor="center")
        self.tree.column("name", width=280, anchor="w")
        self.tree.column("score", width=120, anchor="center")

        # Row color tags
        self.tree.tag_configure("gold", background="#2A1F00", foreground="#FFD166")
        self.tree.tag_configure("silver", background="#1A1F2A", foreground="#C7D3DD")
        self.tree.tag_configure("bronze", background="#2A140A", foreground="#D4A373")
        self.tree.tag_configure("odd", background="#0B0F1A", foreground="#EDEDED")
        self.tree.tag_configure("even", background="#0E1424", foreground="#EDEDED")

        self.tree.pack(fill="both", expand=True, padx=8, pady=8)

        self.scan_ports()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _ensure_csv_exists(self):
        if not os.path.exists(CSV_PATH):
            with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["name", "score"])

    def scan_ports(self):
        ports = [p.device for p in list_ports.comports()]
        self.port_combo["values"] = ports
        if ports and not self.port_var.get():
            self.port_var.set(ports[0])

    def connect(self):
        if self.ser:
            return
        port = self.port_var.get().strip()
        if not port:
            messagebox.showerror("Port", "Select a serial port first.")
            return

        try:
            self.ser = serial.Serial(port, 9600, timeout=0.2)
            time.sleep(2.0)  # Arduino reset on connect
            self.ser.reset_input_buffer()
            self.status_var.set(f"Connected to {port}")
        except Exception as e:
            self.ser = None
            messagebox.showerror("Connect failed", str(e))
            return

        self.stop_reader.clear()
        self.reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self.reader_thread.start()

    def disconnect(self):
        self.stop_reader.set()
        if self.ser:
            try:
                self.ser.close()
            except:
                pass
        self.ser = None
        self.status_var.set("Not connected")
        self.game_running = False

    def start_game(self):
        if not self.ser:
            messagebox.showerror("Not connected", "Connect to Arduino first.")
            return

        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("Name", "Enter a player name.")
            return

        if self.game_running:
            messagebox.showinfo("Game running", "A game is already running.")
            return

        self.now_playing_var.set(f"Now Playing: {name}")
        self.current_player = name
        self.session_points = 0
        self.session_var.set("Session points: 0")
        self.game_running = True

        try:
            self.ser.write(b"START\n")
        except Exception as e:
            self.game_running = False
            messagebox.showerror("Serial write failed", str(e))

    def _reader_loop(self):
        buffer = ""
        while not self.stop_reader.is_set():
            if not self.ser:
                time.sleep(0.1)
                continue
            try:
                data = self.ser.read(256)
                if not data:
                    time.sleep(0.05)
                    continue
                buffer += data.decode(errors="ignore")

                # split on any line ending
                while "\n" in buffer or "\r" in buffer:
                    line, sep, rest = buffer.partition("\n")
                    if sep == "":
                        line, sep, rest = buffer.partition("\r")
                    buffer = rest
                    line = line.strip()
                    if line:
                        self._handle_line(line)
            except Exception:
                self.disconnect()
                break

    def _handle_line(self, line: str):
        if line == "READY":
            return
        if not self.game_running:
            return

        if line == "TRY_PASS":
            self.session_points += POINTS_PER_TRY_PASS
            self.after(0, lambda: self.session_var.set(f"Session points: {self.session_points}"))

        elif line == "TRY_FAIL":
            self.after(0, lambda: self.session_var.set(f"Session points: {self.session_points}"))

        elif line == "GAME_WIN":
            self.session_points += WIN_BONUS
            self._update_csv_score(self.current_player, self.session_points)
            self.after(0, lambda: messagebox.showinfo(
                "Game finished",
                f"{self.current_player} WON!\nSession points: {self.session_points}\n(+{WIN_BONUS} win bonus)\n\nPress Refresh to update leaderboard."
            ))
            self.game_running = False
            self.after(0, lambda: self.now_playing_var.set("Now Playing: —"))

        elif line == "GAME_OVER":
            self._update_csv_score(self.current_player, self.session_points)
            self.after(0, lambda: messagebox.showinfo(
                "Game finished",
                f"{self.current_player} LOST.\nSession points: {self.session_points}\n\nPress Refresh to update leaderboard."
            ))
            self.game_running = False
            self.after(0, lambda: self.now_playing_var.set("Now Playing: —"))

    def _read_scores(self):
        scores = {}
        if not os.path.exists(CSV_PATH):
            return scores
        with open(CSV_PATH, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = (row.get("name") or "").strip()
                if not name:
                    continue
                try:
                    score = int(row.get("score") or 0)
                except:
                    score = 0
                scores[name] = score
        return scores

    def _write_scores(self, scores: dict):
        with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["name", "score"])
            for name, score in scores.items():
                writer.writerow([name, score])

    def _update_csv_score(self, name: str, delta_points: int):
        scores = self._read_scores()
        scores[name] = int(scores.get(name, 0)) + int(delta_points)
        self._write_scores(scores)

    def refresh_leaderboard(self):
        scores = self._read_scores()
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        # Clear existing
        for item in self.tree.get_children():
            self.tree.delete(item)

        for i, (name, score) in enumerate(ranked, start=1):
            if i == 1:
                tag = "gold"
            elif i == 2:
                tag = "silver"
            elif i == 3:
                tag = "bronze"
            else:
                tag = "even" if (i % 2 == 0) else "odd"

            self.tree.insert("", "end", values=(i, name, score), tags=(tag,))

    def _setup_styles(self):
        style = ttk.Style(self)
        # Use a consistent theme; 'clam' is easiest to style
        style.theme_use("clam")

        # General
        style.configure("TFrame", background="#121212")
        style.configure("TLabelframe", background="#121212", foreground="#EDEDED")
        style.configure("TLabelframe.Label", background="#121212", foreground="#EDEDED")
        style.configure("TLabel", background="#121212", foreground="#EDEDED")
        style.configure("TButton", padding=6)

        # Treeview (leaderboard)
        style.configure(
            "Arcade.Treeview",
            background="#0B0F1A",
            fieldbackground="#0B0F1A",
            foreground="#EDEDED",
            rowheight=28,
            borderwidth=0,
        )
        style.configure(
            "Arcade.Treeview.Heading",
            background="#1E2A44",
            foreground="#FFFFFF",
            relief="flat",
        )
        style.map(
            "Arcade.Treeview.Heading",
            background=[("active", "#2A3A5F")],
        )

    def on_close(self):
        self.disconnect()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
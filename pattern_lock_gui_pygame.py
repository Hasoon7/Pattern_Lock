import csv
import os
import threading
import time

import pygame
import serial
from serial.tools import list_ports

# ========= Settings =========
CSV_PATH = "leaderboard.csv"
BAUD = 9600

POINTS_PER_TRY_PASS = 1
WIN_BONUS = 5

WIDTH, HEIGHT = 1500, 800
FPS = 60

# Colors
BG = (10, 14, 26)
PANEL = (16, 22, 40)
PANEL2 = (20, 28, 52)
BORDER = (70, 110, 190)

WHITE = (235, 235, 235)
MUTED = (170, 180, 210)
CYAN = (53, 242, 255)
PINK = (255, 61, 245)
GREEN = (112, 255, 170)

GOLD = (255, 209, 102)
SILVER = (199, 211, 221)
BRONZE = (212, 163, 115)

# ========= CSV helpers =========
def ensure_csv_exists():
    if not os.path.exists(CSV_PATH):
        with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["name", "score"])

def read_scores():
    scores = {}
    if not os.path.exists(CSV_PATH):
        return scores
    with open(CSV_PATH, "r", newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            name = (row.get("name") or "").strip()
            if not name:
                continue
            try:
                score = int(row.get("score") or 0)
            except:
                score = 0
            scores[name] = score
    return scores

def write_scores(scores: dict):
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["name", "score"])
        for name, score in scores.items():
            w.writerow([name, int(score)])

def add_points(name: str, delta: int):
    scores = read_scores()
    scores[name] = int(scores.get(name, 0)) + int(delta)
    write_scores(scores)

# ========= UI components =========
class Button:
    def __init__(self, rect, text, font, bg=PANEL2, fg=WHITE, hover=(40, 55, 95)):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.font = font
        self.bg = bg
        self.fg = fg
        self.hover = hover

    def draw(self, screen, mouse_pos):
        color = self.hover if self.rect.collidepoint(mouse_pos) else self.bg
        pygame.draw.rect(screen, color, self.rect, border_radius=12)
        pygame.draw.rect(screen, BORDER, self.rect, width=2, border_radius=12)
        surf = self.font.render(self.text, True, self.fg)
        screen.blit(surf, surf.get_rect(center=self.rect.center))

    def clicked(self, mouse_pos, mouse_down):
        return mouse_down and self.rect.collidepoint(mouse_pos)

class TextInput:
    def __init__(self, rect, font, placeholder="Enter name..."):
        self.rect = pygame.Rect(rect)
        self.font = font
        self.placeholder = placeholder
        self.text = ""
        self.active = False

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(event.pos)

        if event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                pass
            else:
                if len(self.text) < 24 and event.unicode.isprintable():
                    self.text += event.unicode

    def draw(self, screen):
        pygame.draw.rect(screen, PANEL2, self.rect, border_radius=12)
        pygame.draw.rect(screen, PINK if self.active else BORDER, self.rect, width=2, border_radius=12)

        show = self.text if self.text else self.placeholder
        color = WHITE if self.text else MUTED
        surf = self.font.render(show, True, color)
        screen.blit(surf, (self.rect.x + 12, self.rect.y + (self.rect.height - surf.get_height()) // 2))

# ========= Serial manager =========
class SerialManager:
    def __init__(self):
        self.ser = None
        self.port = None
        self.thread = None
        self.stop = threading.Event()
        self.on_line = None

    def connect(self, port):
        self.disconnect()
        self.port = port
        self.ser = serial.Serial(port, BAUD, timeout=0.2)
        time.sleep(2.0)  # Arduino reset
        try:
            self.ser.reset_input_buffer()
        except:
            pass
        self.stop.clear()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def disconnect(self):
        self.stop.set()
        if self.ser:
            try:
                self.ser.close()
            except:
                pass
        self.ser = None
        self.port = None

    def send_start(self):
        if self.ser:
            self.ser.write(b"START\n")

    def _loop(self):
        buf = ""
        while not self.stop.is_set():
            if not self.ser:
                time.sleep(0.1)
                continue
            try:
                data = self.ser.read(256)
                if not data:
                    time.sleep(0.05)
                    continue
                buf += data.decode(errors="ignore")
                while "\n" in buf or "\r" in buf:
                    line, sep, rest = buf.partition("\n")
                    if sep == "":
                        line, sep, rest = buf.partition("\r")
                    buf = rest
                    line = line.strip()
                    if line and self.on_line:
                        self.on_line(line)
            except Exception:
                self.disconnect()
                break

# ========= Layout helpers =========
def draw_panel(screen, rect, title, title_font):
    pygame.draw.rect(screen, PANEL, rect, border_radius=18)
    pygame.draw.rect(screen, BORDER, rect, width=2, border_radius=18)
    t = title_font.render(title, True, WHITE)
    screen.blit(t, (rect.x + 16, rect.y + 14))

def list_serial_ports():
    return [p.device for p in list_ports.comports()]

def load_font(preferred_name, size, fallback="consolas"):
    try:
        p = pygame.font.match_font(preferred_name)
        if p:
            return pygame.font.Font(p, size)
    except:
        pass
    try:
        p = pygame.font.match_font(fallback)
        if p:
            return pygame.font.Font(p, size)
    except:
        pass
    return pygame.font.Font(None, size)

# ========= Main app =========
def main():
    ensure_csv_exists()
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Pattern Lock - Leaderboard (pygame)")
    clock = pygame.time.Clock()

    # Fonts (pixel if installed; safe fallbacks)
    title_font = pygame.font.Font("PressStart2P-Regular.ttf", 32)
    h_font = pygame.font.Font("PressStart2P-Regular.ttf", 24)
    ui_font = pygame.font.Font("PressStart2P-Regular.ttf", 20)
    small_font = pygame.font.Font("PressStart2P-Regular.ttf", 14)
    mono_font = pygame.font.Font("PressStart2P-Regular.ttf", 14)

    ports = list_serial_ports()
    port_index = 0 if ports else -1

    serial_mgr = SerialManager()

    # State
    status = "Not connected"
    current_player = None
    now_playing = "—"
    session_points = 0
    game_running = False
    last_game_msg = ""

    leaderboard = []

    def refresh_leaderboard():
        nonlocal leaderboard
        scores = read_scores()
        leaderboard = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    refresh_leaderboard()

    # Serial inbox from thread -> main loop
    inbox = []
    inbox_lock = threading.Lock()

    def on_line(line):
        with inbox_lock:
            inbox.append(line)

    serial_mgr.on_line = on_line

    # ===== Panels geometry (fixed + clean) =====
    PAD = 22
    header_h = 120

    left_rect = pygame.Rect(PAD, header_h, 660, HEIGHT - header_h - PAD)
    right_rect = pygame.Rect(left_rect.right + PAD, header_h, WIDTH - left_rect.right - 2 * PAD, HEIGHT - header_h - PAD)

    # Inside left panel: we’ll place elements with a y-cursor
    def left_content_origin():
        return left_rect.x + 16, left_rect.y + 54

    def right_content_origin():
        return right_rect.x + 16, right_rect.y + 54

    # UI elements (created with placeholder rects; updated each frame from layout)
    name_input = TextInput((0, 0, 0, 0), small_font, placeholder="Enter player name...")

    btn_scan = Button((0, 0, 140, 44), "Scan", small_font)
    btn_prev = Button((0, 0, 44, 44), "<", small_font)
    btn_next = Button((0, 0, 44, 44), ">", small_font)
    btn_connect = Button((0, 0, 120, 44), "Connect", small_font)
    btn_disconnect = Button((0, 0, 140, 44), "Disconnect", small_font)

    btn_start = Button((0, 0, 180, 52), "Start Game", small_font)
    btn_refresh = Button((0, 0, 140, 44), "Refresh", small_font)

    running = True
    while running:
        clock.tick(FPS)

        mouse_pos = pygame.mouse.get_pos()
        mouse_down = False

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mouse_down = True

            name_input.handle_event(event)

            if event.type == pygame.KEYDOWN:
                # Enter starts game if not typing in the name box
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and not name_input.active:
                    if serial_mgr.ser and not game_running:
                        nm = name_input.text.strip()
                        if nm:
                            current_player = nm
                            now_playing = nm
                            session_points = 0
                            last_game_msg = ""
                            game_running = True
                            serial_mgr.send_start()

        # ===== Buttons: click handling =====
        if btn_scan.clicked(mouse_pos, mouse_down):
            ports = list_serial_ports()
            port_index = 0 if ports else -1

        if btn_prev.clicked(mouse_pos, mouse_down) and ports:
            port_index = (port_index - 1) % len(ports)

        if btn_next.clicked(mouse_pos, mouse_down) and ports:
            port_index = (port_index + 1) % len(ports)

        if btn_connect.clicked(mouse_pos, mouse_down):
            if ports and port_index >= 0:
                try:
                    serial_mgr.connect(ports[port_index])
                    status = f"Connected to {ports[port_index]}"
                except Exception as e:
                    status = f"Connect failed: {e}"

        if btn_disconnect.clicked(mouse_pos, mouse_down):
            serial_mgr.disconnect()
            status = "Not connected"
            game_running = False
            now_playing = "—"

        if btn_start.clicked(mouse_pos, mouse_down):
            if not serial_mgr.ser:
                status = "Not connected (connect first)"
            elif game_running:
                status = "Game already running"
            else:
                nm = name_input.text.strip()
                if not nm:
                    status = "Enter a name first"
                else:
                    current_player = nm
                    now_playing = nm
                    session_points = 0
                    last_game_msg = ""
                    game_running = True
                    serial_mgr.send_start()

        if btn_refresh.clicked(mouse_pos, mouse_down):
            refresh_leaderboard()

        # ===== Consume serial lines =====
        with inbox_lock:
            lines = inbox[:]
            inbox.clear()

        for line in lines:
            if line == "READY":
                continue
            if not game_running:
                continue

            if line == "TRY_PASS":
                session_points += POINTS_PER_TRY_PASS

            elif line == "TRY_FAIL":
                pass

            elif line == "GAME_WIN":
                session_points += WIN_BONUS
                if current_player:
                    add_points(current_player, session_points)
                last_game_msg = f"{current_player} WON! +{session_points} points (incl. +{WIN_BONUS} bonus)."
                game_running = False
                now_playing = "—"

            elif line == "GAME_OVER":
                if current_player:
                    add_points(current_player, session_points)
                last_game_msg = f"{current_player} LOST. +{session_points} points."
                game_running = False
                now_playing = "—"

        # ========= DRAW =========
        screen.fill(BG)

        # Header
        t_shadow = title_font.render("PATTERN LOCK", True, (0, 120, 140))
        t_main = title_font.render("PATTERN LOCK", True, CYAN)
        screen.blit(t_shadow, t_shadow.get_rect(center=(WIDTH // 2 + 2, 56 + 2)))
        screen.blit(t_main, t_main.get_rect(center=(WIDTH // 2, 56)))

        sub = h_font.render("Arduino Memory Challenge • Leaderboard", True, MUTED)
        screen.blit(sub, sub.get_rect(center=(WIDTH // 2, 96)))

        # Panels
        draw_panel(screen, left_rect, "CONTROL", h_font)
        draw_panel(screen, right_rect, "LEADERBOARD", h_font)

        # ----- Left panel content with y-cursor -----
        lx, y = left_content_origin()
        line_gap = 12

        # Connection row
        label = ui_font.render("Connection", True, WHITE)
        screen.blit(label, (lx, y))
        y += label.get_height() + 10

        # Buttons row (scan, <, >, connect, disconnect)
        row_h = 44
        x = lx
        btn_scan.rect.topleft = (x, y)
        x += btn_scan.rect.width + 10
        btn_prev.rect.topleft = (x, y)
        x += btn_prev.rect.width + 8
        btn_next.rect.topleft = (x, y)
        x += btn_next.rect.width + 16
        btn_connect.rect.topleft = (x, y)
        x += btn_connect.rect.width + 10
        btn_disconnect.rect.topleft = (x, y)

        btn_scan.draw(screen, mouse_pos)
        btn_prev.draw(screen, mouse_pos)
        btn_next.draw(screen, mouse_pos)
        btn_connect.draw(screen, mouse_pos)
        btn_disconnect.draw(screen, mouse_pos)

        y += row_h + 10

        # Port + status lines (no overlap)
        port_text = ports[port_index] if ports and port_index >= 0 else "No ports"
        port_line = small_font.render(f"Port: {port_text}", True, WHITE)
        screen.blit(port_line, (lx, y))
        y += port_line.get_height() + 4

        status_line = small_font.render(f"Status: {status}", True, MUTED)
        screen.blit(status_line, (lx, y))
        y += status_line.get_height() + 18

        # Player section
        p_label = ui_font.render("Player", True, WHITE)
        screen.blit(p_label, (lx, y))
        y += p_label.get_height() + 10

        # Name input + start button row
        input_w = 420
        input_h = 52
        name_input.rect = pygame.Rect(lx, y, input_w, input_h)
        btn_start.rect = pygame.Rect(lx + input_w + 16, y, 180, input_h)

        name_input.draw(screen)
        btn_start.draw(screen, mouse_pos)

        y += input_h + 26

        # Now playing (centered, separate zone below panels top; no collisions)
        now_surf = ui_font.render(f"Now Playing: {now_playing}", True, PINK)
        screen.blit(now_surf, now_surf.get_rect(center=(left_rect.centerx, y)))
        y += now_surf.get_height() + 10

        pts_color = GREEN if game_running else WHITE
        pts_surf = ui_font.render(f"Session points: {session_points}", True, pts_color)
        screen.blit(pts_surf, pts_surf.get_rect(center=(left_rect.centerx, y)))
        y += pts_surf.get_height() + 14

        if last_game_msg:
            msg = small_font.render(last_game_msg, True, WHITE)
            screen.blit(msg, msg.get_rect(center=(left_rect.centerx, y)))

        # ----- Right panel -----
        rx, ry = right_content_origin()

        # Top row: small hint + refresh button (no overlap)
        hint = small_font.render("Press Refresh after a game", True, MUTED)
        screen.blit(hint, (rx, ry))

        btn_refresh.rect.topleft = (right_rect.right - 16 - btn_refresh.rect.width, ry - 6)
        btn_refresh.draw(screen, mouse_pos)

        ry += hint.get_height() + 16

        # Table header
        header = mono_font.render("Rank  Name                Score", True, MUTED)
        screen.blit(header, (rx, ry))
        ry += header.get_height() + 10

        # Rows
        max_rows = 14
        for i, (name, score) in enumerate(leaderboard[:max_rows], start=1):
            if i == 1:
                color = GOLD
            elif i == 2:
                color = SILVER
            elif i == 3:
                color = BRONZE
            else:
                color = WHITE

            row = f"{i:<4}  {name[:18]:<18}      {score:>4}"
            row_surf = mono_font.render(row, True, color)
            screen.blit(row_surf, (rx, ry))
            ry += row_surf.get_height() + 8

        pygame.display.flip()

    serial_mgr.disconnect()
    pygame.quit()


if __name__ == "__main__":
    main()
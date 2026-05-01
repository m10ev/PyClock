import tkinter as tk
import requests
import pystray
from PIL import Image, ImageDraw
import webbrowser
from tkinter import messagebox
import threading
import math
import time
import json
import os

# CONFIG
CLOCK_SIZE = 200
RADIUS = 88
FACE_ALPHA = 1.0
SAVE_FILE = "clock_settings.json"

THEMES = {
    "dark": {
        "bg": "#1e1e2e",
        "face": "#2b2b3b",
        "text": "#cdd6f4",
        "date": "#a6adc8",
        "second": "#f38ba8",
        "hand": "#cdd6f4",
        "ticks": "#585b70"
    },
    "light": {
        "bg": "#ffffff",
        "face": "#f2f2f2",
        "text": "#11111b",
        "date": "#45475a",
        "second": "#e74c3c",
        "hand": "#11111b",
        "ticks": "#bac2de"
    }
}

class ClockOverlay:
    def __init__(self, root):
        self.root = root
        self.root.title("Clock Overlay")
        self.root.overrideredirect(True)
        self.root.wm_attributes("-topmost", True)

        self._after_id = None

        # State Variables
        self.theme_name = tk.StringVar(value="dark")
        self.use_24h = tk.BooleanVar(value=False)
        self.show_date = tk.BooleanVar(value=True)
        self.scale = tk.DoubleVar(value=1.0)
        self.is_fullscreen = False
        self.start_on_boot = tk.BooleanVar(value=False)

        self._drag_x = 0
        self._drag_y = 0

        self._load_settings()
        self._build_ui()
        self._apply_theme()
        self._setup_tray()

        # Initial Position
        sw = self.root.winfo_screenwidth()
        self.root.geometry(f"+{sw - 300}+50")

        self._tick()

        self._check_for_updates()


    def _build_ui(self):
        self.container = tk.Frame(self.root)
        self.container.pack(expand=True)

        self.canvas = tk.Canvas(self.container, bd=0, highlightthickness=0)
        self.canvas.pack()

        self.digital_lbl = tk.Label(self.container, font=("Segoe UI", 24, "bold"))
        self.digital_lbl.pack()

        self.date_lbl = tk.Label(self.container, font=("Segoe UI", 10))
        self.date_lbl.pack()

        # Interaction Binding
        for w in (self.root, self.container, self.canvas, self.digital_lbl, self.date_lbl):
            w.bind("<ButtonPress-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)
            w.bind("<Button-3>", self._show_menu)
            w.bind("<Double-Button-1>", lambda e: self._toggle_fullscreen())

        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="Toggle Fullscreen (F11)", command=self._toggle_fullscreen)
        self.menu.add_separator()
        self.menu.add_command(label="Dark Theme", command=lambda: self._set_theme("dark"))
        self.menu.add_command(label="Light Theme", command=lambda: self._set_theme("light"))
        self.menu.add_separator()
        self.menu.add_checkbutton(label="24h Mode", variable=self.use_24h, command=self._save_settings)
        self.menu.add_checkbutton(label="Show Date", variable=self.show_date, command=self._save_settings)
        self.menu.add_separator()
        self.menu.add_command(label="Scale +", command=lambda: self._change_scale(0.1))
        self.menu.add_command(label="Scale -", command=lambda: self._change_scale(-0.1))
        self.menu.add_separator()
        self.menu.add_checkbutton(
            label="Run on Startup",
            variable=self.start_on_boot,
            command=self._toggle_startup
        )
        self.menu.add_separator()
        self.menu.add_command(label="Exit", command=self._graceful_exit)

        self.root.protocol("WM_DELETE_WINDOW", self._graceful_exit)

        self.root.bind("<F11>", lambda e: self._toggle_fullscreen())
        self.root.bind("<Escape>", lambda e: self._exit_fullscreen())

    def _save_settings(self):
        data = {
            "theme": self.theme_name.get(),
            "scale": self.scale.get(),
            "use_24h": self.use_24h.get(),
            "show_date": self.show_date.get(),
            "start_on_boot": self.start_on_boot.get()
        }
        with open(SAVE_FILE, "w") as f:
            json.dump(data, f)

    def _load_settings(self):
        """Loads state from JSON file if it exists."""
        if os.path.exists(SAVE_FILE):
            try:
                with open(SAVE_FILE, "r") as f:
                    data = json.load(f)
                    self.theme_name.set(data.get("theme", "dark"))
                    self.scale.set(data.get("scale", 1.0))
                    self.use_24h.set(data.get("use_24h", False))
                    self.show_date.set(data.get("show_date", True))
                    self.start_on_boot.set(data.get("start_on_boot", False))
            except:
                pass

    def _apply_theme(self):
        t = THEMES[self.theme_name.get()]
        self.root.configure(bg=t["bg"])

        # In fullscreen, we don't want transparency
        if not self.is_fullscreen:
            self.root.wm_attributes("-transparentcolor", t["bg"])
        else:
            self.root.wm_attributes("-transparentcolor", "")

        self.container.configure(bg=t["bg"])
        self.canvas.configure(bg=t["bg"])
        self.digital_lbl.configure(bg=t["bg"], fg=t["text"])
        self.date_lbl.configure(bg=t["bg"], fg=t["date"])
        self._apply_scale()

    def _toggle_fullscreen(self):
        self.is_fullscreen = not self.is_fullscreen

        # Withdraw to prevent visual flickering during the transition
        self.root.withdraw()

        try:
            if self.is_fullscreen:
                # We force a small update to ensure the window exists in the OS eye
                self.root.update_idletasks()
                self.root.overrideredirect(False)
                self.root.attributes("-fullscreen", True)
            else:
                self.root.attributes("-fullscreen", False)
                self.root.update_idletasks()
                self.root.overrideredirect(True)
        except tk.TclError:
            # If the error occurs, we ignore it because the state
            # usually changes correctly regardless of the return value
            pass

        # Use 'after' to ensure the OS has processed the state change
        # before bringing the window back
        self.root.after(100, lambda: (self.root.deiconify(), self._apply_theme()))

    def _exit_fullscreen(self):
        if self.is_fullscreen:
            self._toggle_fullscreen()

    def _apply_scale(self):
        s = self.scale.get()
        size = int(CLOCK_SIZE * s)
        self.center = size // 2
        self.radius = int(RADIUS * s)
        self.canvas.config(width=size, height=size)
        self.canvas.delete("all")
        self._draw_face()

    def _change_scale(self, delta):
        new_val = round(max(0.5, min(3.0, self.scale.get() + delta)), 1)
        self.scale.set(new_val)
        self._apply_scale()
        self._save_settings()

    def _set_theme(self, name):
        self.theme_name.set(name)
        self._apply_theme()
        self._save_settings()

    def _draw_face(self):
        self.canvas.delete("all")
        t = THEMES[self.theme_name.get()]
        cx, cy, r = self.center, self.center, self.radius
        self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=t["face"], outline=t["ticks"], width=2)

        for i in range(60):
            angle = math.radians(i * 6 - 90)
            is_hour = (i % 5 == 0)
            r1 = r - (12 * self.scale.get() if is_hour else 6 * self.scale.get())
            r2 = r - 4
            x1, y1 = cx + r1 * math.cos(angle), cy + r1 * math.sin(angle)
            x2, y2 = cx + r2 * math.cos(angle), cy + r2 * math.sin(angle)
            self.canvas.create_line(x1, y1, x2, y2, fill=t["ticks"], width=2 if is_hour else 1)

        self.hour_hand = self.canvas.create_line(0, 0, 0, 0, width=4, fill=t["hand"], capstyle="round")
        self.min_hand = self.canvas.create_line(0, 0, 0, 0, width=3, fill=t["hand"], capstyle="round")
        self.sec_hand = self.canvas.create_line(0, 0, 0, 0, width=1, fill=t["second"])

    def _setup_tray(self):
        """Creates a system tray icon with a toolbox-style look."""
        # Create a simple icon image (or load an .ico file)
        width, height = 64, 64
        image = Image.new('RGB', (width, height), (30, 30, 46))  # Dark background
        dc = ImageDraw.Draw(image)
        # Draw a simple toolbox/wrench shape
        dc.rectangle([10, 20, 54, 50], fill="#cdd6f4")
        dc.rectangle([25, 10, 39, 20], outline="#cdd6f4", width=4)

        # Inside _setup_tray
        menu = pystray.Menu(
            pystray.MenuItem("Show/Hide", self._toggle_visibility),
            pystray.MenuItem("Exit", lambda icon, item: self._graceful_exit())
        )

        self.tray = pystray.Icon("ClockOverlay", image, "Clock Overlay", menu)
        # Run tray in a separate thread so it doesn't freeze the clock
        threading.Thread(target=self.tray.run, daemon=True).start()

    def _toggle_visibility(self):
        """Standard tray functionality to show/hide the clock."""
        if self.root.winfo_viewable():
            self.root.withdraw()
        else:
            self.root.deiconify()

    def _tick(self):
        now = time.localtime()
        t_sec = time.time() % 60
        t_min = now.tm_min + t_sec / 60
        t_hrs = (now.tm_hour % 12) + t_min / 60

        def get_coords(angle, length_mult):
            rad = math.radians(angle - 90)
            return self.center, self.center, self.center + (self.radius * length_mult) * math.cos(rad), self.center + (
                        self.radius * length_mult) * math.sin(rad)

        self.canvas.coords(self.hour_hand, *get_coords(t_hrs * 30, 0.5))
        self.canvas.coords(self.min_hand, *get_coords(t_min * 6, 0.75))
        self.canvas.coords(self.sec_hand, *get_coords(t_sec * 6, 0.85))

        fmt = "%H:%M:%S" if self.use_24h.get() else "%I:%M:%S %p"
        self.digital_lbl.config(text=time.strftime(fmt))

        if self.show_date.get():
            self.date_lbl.config(text=time.strftime("%A, %b %d"))
            self.date_lbl.pack()
        else:
            self.date_lbl.pack_forget()

        self._after_id = self.root.after(100, self._tick)

    def _show_menu(self, e):
        self.menu.tk_popup(e.x_root, e.y_root)

    def _drag_start(self, e):
        self._drag_x = e.x_root - self.root.winfo_x()
        self._drag_y = e.y_root - self.root.winfo_y()

    def _drag_move(self, e):
        if not self.is_fullscreen:
            self.root.geometry(f"+{e.x_root - self._drag_x}+{e.y_root - self._drag_y}")

    def _check_for_updates(self):
        """Checks GitHub for a new release and asks to redirect."""
        current_version = "PyClock v1.1.0"
        repo = "m10ev/PyClock"

        try:
            # Use a short timeout so the app doesn't freeze if the internet is slow
            response = requests.get(
                f"https://api.github.com/repos/{repo}/releases/latest",
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                latest_version = data.get("name", "")
                download_url = data.get("html_url", "")

                if latest_version and latest_version != current_version:
                    # This pops a real window that won't be missed
                    if messagebox.askyesno(
                            "Update Available",
                            f"A new version ({latest_version}) is available!\n\n"
                            "Would you like to open the download page?"
                    ):
                        webbrowser.open(download_url)
        except Exception:
            pass

    def _toggle_startup(self):
        import winreg as reg
        import sys

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "ClockOverlay"

        # If running as an EXE, sys.executable is the path to your EXE.
        # If running as a script, it's the path to python.exe.
        exe_path = os.path.realpath(sys.executable)

        try:
            key = reg.OpenKey(reg.HKEY_CURRENT_USER, key_path, 0, reg.KEY_ALL_ACCESS)
            if self.start_on_boot.get():
                # Add to registry
                reg.SetValueEx(key, app_name, 0, reg.REG_SZ, f'"{exe_path}"')
            else:
                # Remove from registry
                try:
                    reg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass
            reg.CloseKey(key)
        except Exception as e:
            print(f"Registry error: {e}")

        self._save_settings()

    def _graceful_exit(self):
        self.is_running = False

        # 1. Stop the tray icon immediately so it vanishes from the taskbar
        if hasattr(self, 'tray'):
            try:
                self.tray.stop()
            except:
                pass

        # 2. Stop the clock loop so it doesn't try to draw on a dead canvas
        if self._after_id:
            try:
                self.root.after_cancel(self._after_id)
            except:
                pass

        # 3. DESTROY THE WHITE BOX: Force Windows to refresh the screen area
        try:
            self.root.overrideredirect(False)  # Tell Windows it's a 'real' window again
            self.root.withdraw()  # Hide it immediately
            self.root.update_idletasks()  # Flush the UI queue
        except:
            pass

        # 4. Final Process Kill
        self.root.quit()
        # A tiny delay ensures the tray.stop() and withdraw() finish before destruction
        self.root.after(100, self.root.destroy)

if __name__ == "__main__":
    root = tk.Tk()
    app = ClockOverlay(root)
    root.mainloop()
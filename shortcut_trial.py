"""One paired Switch button mapped to a shortcut chosen on Windows."""

import ctypes
import secrets
import threading
import time


SHORTCUTS = {"Ctrl+F": ord("F"), "Ctrl+A": ord("A")}


class KeyboardInput(ctypes.Structure):
    _fields_ = [
        ("vk", ctypes.c_uint16), ("scan", ctypes.c_uint16),
        ("flags", ctypes.c_uint32), ("time", ctypes.c_uint32),
        ("extra", ctypes.c_size_t),
    ]


class MouseInput(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_int32), ("y", ctypes.c_int32), ("data", ctypes.c_uint32),
        ("flags", ctypes.c_uint32), ("time", ctypes.c_uint32), ("extra", ctypes.c_size_t),
    ]


class InputData(ctypes.Union):
    _fields_ = [("keyboard", KeyboardInput), ("mouse", MouseInput)]


class Input(ctypes.Structure):
    _fields_ = [("kind", ctypes.c_uint32), ("data", InputData)]


def send_inputs(items):
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    send = user32.SendInput
    send.argtypes = [ctypes.c_uint, ctypes.POINTER(Input), ctypes.c_int]
    send.restype = ctypes.c_uint
    return send(len(items), items, ctypes.sizeof(Input))


def keyboard_events(events):
    """Return the number of events Windows inserted, in order."""
    items = (Input * len(events))()
    for item, (vk, up) in zip(items, events):
        item.kind = 1
        extended = vk in (0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x5B) or 0xAD <= vk <= 0xB3
        item.data.keyboard = KeyboardInput(vk, 0, (2 if up else 0) | int(extended), 0, 0)
    return send_inputs(items)


def type_text(text):
    encoded = text.encode("utf-16-le")
    items = (Input * len(encoded))()
    for index in range(0, len(encoded), 2):
        unit = int.from_bytes(encoded[index:index + 2], "little")
        for up in (0, 1):
            item = items[index + up]
            item.kind = 1
            item.data.keyboard = KeyboardInput(0, unit, 4 | (up * 2), 0, 0)
    send_paired_inputs(items)


def send_paired_inputs(items):
    """Release a partially inserted down/up pair without repeating the action."""
    sent = send_inputs(items)
    if sent != len(items):
        if sent % 2:
            send_inputs((Input * 1)(items[sent]))
        raise OSError("Windows accepted only part of the input.")


def pointer_input(action, dx=0, dy=0):
    if action == "move":
        flags = (0x0001,)
    elif action == "point":
        flags = (0x8001,)  # Absolute movement, normalized to the primary display.
    elif action == "left":
        flags = (0x0002, 0x0004)
    elif action == "right":
        flags = (0x0008, 0x0010)
    else:
        raise ValueError("Unknown pointer action.")
    items = (Input * len(flags))()
    for item, flag in zip(items, flags):
        item.kind = 0
        item.data.mouse = MouseInput(dx, dy, 0, flag, 0, 0)
    send_paired_inputs(items)


def key_pressed(vk):
    return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)


def send_shortcut(name):
    key = SHORTCUTS[name]
    if any(key_pressed(vk) for vk in (0x10, 0x11, 0x12, 0x5B, 0x5C, key)):
        raise OSError("Release the Windows keyboard keys before testing.")

    events = [(0x11, False), (key, False), (key, True), (0x11, True)]
    count = keyboard_events(events)
    if count != len(events):
        releases = {1: [(0x11, True)], 2: [(key, True), (0x11, True)], 3: [(0x11, True)]}
        if count in releases:
            keyboard_events(releases[count])
        raise OSError("Windows did not insert the complete shortcut.")


class PairingSession:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.name = ""
        self.cancelled = threading.Event()
        self.pin = self.token = ""
        self.until = 0

    def arm(self, name):
        with self.lock:
            self.cancelled.set()
            self.cancelled = threading.Event()
            self.name = name
            self.pin = f"{secrets.randbelow(1000000):06d}"
            self.token = ""
            self.until = self.clock() + 300
            self.guesses = self.last_seq = 0
            self.last_sent = float("-inf")
            self.last_move = float("-inf")
            self.last_edit = float("-inf")
            return self.pin

    def disable(self):
        with self.lock:
            self._revoke_locked()

    def _revoke_locked(self):
        self.cancelled.set()
        self.pin = self.token = ""
        self.until = 0

    def status(self):
        with self.lock:
            if self.clock() >= self.until:
                return "Input disabled"
            if self.pin:
                return "Pairing code  " + self.pin
            return f"Paired  ·  {self.name}" if self.token else "Input disabled"

    def pair(self, code):
        with self.lock:
            if not self.pin or self.clock() >= self.until:
                return 403, "On Windows, select Enable pairing."
            if not secrets.compare_digest(code, self.pin):
                self.guesses += 1
                if self.guesses >= 5:
                    self.pin = ""
                return 403, "Check the code on Windows."
            self.pin = ""
            self.token = secrets.token_hex(32)
            self.until = self.clock() + 1200
            return 200, self.token

    def authorized(self, token):
        return bool(self.token and self.clock() < self.until and secrets.compare_digest(self.token, token))

    def accept_sequence(self, sequence, *, movement=False, editing=False):
        if sequence <= self.last_seq:
            return 409, "Already processed."
        self.last_seq = sequence
        now = self.clock()
        if movement:
            if now - self.last_move < 0.025:
                return 429, "Pointer updates are arriving too quickly."
            self.last_move = now
        elif editing:
            if now - self.last_edit < 0.025:
                return 429, "Keyboard input is arriving too quickly."
            self.last_edit = now
        elif now - self.last_sent < 0.3:
            return 429, "Wait briefly and tap again."
        else:
            self.last_sent = now
        return None


class ShortcutTrial(PairingSession):
    def __init__(self, inject=send_shortcut, clock=time.monotonic):
        super().__init__(clock)
        self.inject = inject
        self.name = "Ctrl+F"

    def arm(self, name):
        if name not in SHORTCUTS:
            raise ValueError("Unsupported shortcut")
        return super().arm(name)

    def activate(self, token, sequence):
        with self.lock:
            if not self.authorized(token):
                return 403, "Session ended. Enable pairing on Windows."
            rejected = self.accept_sequence(sequence)
            if rejected:
                return rejected
            try:
                self.inject(self.name)
            except OSError as error:
                return 503, str(error)
            print(f"Windows accepted {self.name} (tap {sequence})", flush=True)
            return 200, "Windows accepted " + self.name


def show_controls(trial):
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title("Switch shortcut trial")
    panel = ttk.Frame(root, padding=20)
    panel.pack(fill="both", expand=True)
    name = tk.StringVar(value="Ctrl+F")
    state = tk.StringVar(value=trial.status())
    received = tk.StringVar(value="Waiting for a shortcut in this window")
    ttk.Label(panel, textvariable=state, font=("Segoe UI", 16)).pack(pady=6)
    ttk.Label(panel, text="Windows shortcut").pack()
    def select(name):
        trial.arm(name)
        root.focus_set()
    ttk.OptionMenu(panel, name, name.get(), *SHORTCUTS, command=lambda _: trial.disable()).pack()
    ttk.Button(panel, text="Enable pairing", command=lambda: select(name.get())).pack(fill="x", pady=4)
    ttk.Button(panel, text="Disable input", command=trial.disable).pack(fill="x")
    ttk.Label(panel, textvariable=received).pack(pady=10)
    count = 0

    def observed(event):
        nonlocal count
        count += 1
        received.set(f"Received Ctrl+{event.keysym.upper()} in this window ({count})")
        return "break"

    root.bind("<Control-f>", observed)
    root.bind("<Control-a>", observed)

    def refresh():
        state.set(trial.status())
        root.after(250, refresh)

    refresh()
    try:
        root.mainloop()
    finally:
        trial.disable()

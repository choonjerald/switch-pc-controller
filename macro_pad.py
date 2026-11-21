"""Validated local profiles and cancellable, paired macro execution."""

import ctypes
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import tempfile
import threading

from shortcut_trial import PairingSession, keyboard_events, key_pressed, pointer_input, type_text


EXAMPLES = Path(__file__).with_name("profiles.example.json")
APPS = {"notepad": "notepad.exe", "calculator": "calc.exe"}
KEYS = {key: ord(key) for key in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"}
KEYS.update({f"F{i}": 0x6F + i for i in range(1, 25)})
KEYS.update({
    "Ctrl": 0x11, "Shift": 0x10, "Alt": 0x12, "Win": 0x5B,
    "Backspace": 8, "Tab": 9, "Enter": 13, "Esc": 27, "Space": 32,
    "PageUp": 33, "PageDown": 34, "End": 35, "Home": 36, "Left": 37,
    "Up": 38, "Right": 39, "Down": 40, "Insert": 45, "Delete": 46,
    "Mute": 0xAD, "VolumeDown": 0xAE, "VolumeUp": 0xAF, "NextTrack": 0xB0,
    "PreviousTrack": 0xB1, "MediaStop": 0xB2, "PlayPause": 0xB3,
})
EDIT_KEYS = {
    "backspace": (KEYS["Backspace"],),
    "enter": (KEYS["Enter"],),
    "tab": (KEYS["Tab"],),
    "alt-tab": (KEYS["Alt"], KEYS["Tab"]),
    "switch-open": (KEYS["Ctrl"], KEYS["Alt"], KEYS["Tab"]),
    "switch-left": (KEYS["Left"],),
    "switch-right": (KEYS["Right"],),
    "switch-cancel": (KEYS["Esc"],),
}


def steps_for(lines):
    if not isinstance(lines, list) or not 1 <= len(lines) <= 32:
        raise ValueError("Use 1–32 action lines per button.")
    held = set()
    duration = 0
    steps = []
    for line in lines:
        if not isinstance(line, str) or len(line) > 100:
            raise ValueError("Invalid action line.")
        kind, _, arg = line.strip().partition(" ")
        arg = arg.strip()
        if kind == "wait" and re.fullmatch(r"[0-9]{1,4}", arg):
            ms = int(arg)
            duration += ms
            if ms > 3000 or duration > 8000:
                raise ValueError("Delays allow 3000 ms per step and 8000 ms per macro.")
            steps.append((kind, ms))
        elif kind == "launch" and arg in APPS:
            steps.append((kind, arg))
        elif kind in ("tap", "down", "up"):
            names = arg.split("+")
            if len(names) > 5 or any(k not in KEYS for k in names) or len(set(names)) != len(names):
                raise ValueError(f"Unknown or repeated key in {line!r}.")
            keys = tuple(KEYS[k] for k in names)
            if kind != "tap" and len(keys) != 1:
                raise ValueError("Use one key per down or up step.")
            if kind == "up":
                if keys[0] not in held:
                    raise ValueError(f"{arg} was not pressed by this macro.")
                held.remove(keys[0])
            elif held.intersection(keys):
                raise ValueError(f"Key already held in {line!r}.")
            elif kind == "down":
                held.add(keys[0])
            steps.append((kind, keys))
        else:
            raise ValueError(f"Unknown action {line!r}. Use tap, down, up, wait or launch.")
    if held:
        raise ValueError("Add an up step for every down step.")
    return steps


def valid_text(value, limit, empty=False):
    return isinstance(value, str) and len(value) <= limit and (empty or value.strip()) and all(
        char.isprintable() for char in value)


def validate(profiles):
    if not isinstance(profiles, list) or not 1 <= len(profiles) <= 16:
        raise ValueError("Use 1–16 profiles.")
    names = set()
    for profile in profiles:
        if not isinstance(profile, dict) or set(profile) != {"name", "buttons"}:
            raise ValueError("Each profile needs a name and buttons.")
        name, buttons = profile["name"], profile["buttons"]
        if not valid_text(name, 32) or name.casefold() in names:
            raise ValueError("Choose a unique profile name of 1–32 characters.")
        names.add(name.casefold())
        if not isinstance(buttons, list) or len(buttons) != 9:
            raise ValueError("Each profile has nine positions. Use null for empty slots.")
        for button in buttons:
            if button is None:
                continue
            if not isinstance(button, dict) or set(button) != {"label", "icon", "color", "steps"}:
                raise ValueError("Each button needs label, icon, color and steps.")
            if not valid_text(button["label"], 32) or not valid_text(button["icon"], 8, empty=True):
                raise ValueError("Button labels allow 1–32 characters and icons up to 8.")
            if not isinstance(button["color"], str) or not re.fullmatch(r"#[a-fA-F0-9]{6}", button["color"]):
                raise ValueError("Use a six-digit hex color such as #68d9b9.")
            steps_for(button["steps"])


def read_profiles(path):
    with path.open("rb") as source:
        data = source.read(256 * 1024 + 1)
    if len(data) > 256 * 1024:
        raise ValueError("Profile file exceeds 256 KiB.")
    profiles = json.loads(data.decode("utf-8-sig"))
    validate(profiles)
    return profiles


def save_profiles(path, profiles):
    validate(profiles)
    data = json.dumps(profiles, indent=2, ensure_ascii=False) + "\n"
    if len(data.encode("utf-8")) > 256 * 1024:
        raise ValueError("Profile file exceeds 256 KiB.")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temp:
        pending = Path(temp.name)
    try:
        pending.write_text(data, encoding="utf-8", newline="\n")
        os.replace(pending, path)
    finally:
        pending.unlink(missing_ok=True)


def launch_app(app):
    directory = ctypes.create_unicode_buffer(32768)
    size = ctypes.windll.kernel32.GetSystemDirectoryW(directory, len(directory))
    if not 0 < size < len(directory):
        raise OSError("Cannot locate the Windows system directory.")
    subprocess.Popen([str(Path(directory.value) / APPS[app])], close_fds=True)


class MacroPad(PairingSession):
    def __init__(self, profiles, inject=keyboard_events, pressed=key_pressed, launch=launch_app,
                 pointer=pointer_input, write_text=type_text):
        super().__init__()
        self.execution = threading.Lock()
        self.inject, self.pressed, self.launch = inject, pressed, launch
        self.pointer, self.write_text = pointer, write_text
        self.held = []
        self.release_error = ""
        self.set_profiles(profiles)

    def disable(self):
        super().disable()
        with self.execution:
            try:
                self._release_owned()
            except OSError:
                pass  # Keep the remaining keys for another local recovery attempt.

    def status(self):
        return self.release_error or super().status()

    def set_profiles(self, profiles):
        validate(profiles)
        with self.lock:
            self.cancelled.set()
            self.cancelled = threading.Event()
            self.profiles = profiles
            self.revision = secrets.token_hex(4)
            self.layout = json.dumps({
                "revision": self.revision,
                "profiles": [{"name": p["name"], "buttons": [
                    {k: b[k] for k in ("label", "icon", "color")} if b else None
                    for b in p["buttons"]]} for p in profiles],
            }, ensure_ascii=False)

    def get_layout(self, token):
        with self.lock:
            return (200, self.layout) if self.authorized(token) else (403, "Pair on Windows.")

    def desktop_input(self, token, sequence, kind, value):
        with self.lock:
            if not self.authorized(token):
                return 403, "Pair on Windows."
            movement = False
            if kind in ("text", "typing"):
                max_bytes = 48 if kind == "typing" else 512
                if not 1 <= len(value.encode("utf-16-le")) <= max_bytes or any(
                    ord(c) < 32 or 127 <= ord(c) < 160 or c in "\u2028\u2029" for c in value
                ):
                    return 400, "Invalid text length or character."
            elif kind == "edit":
                if value not in EDIT_KEYS:
                    return 400, "Unknown editing key."
            elif kind == "pointer":
                move = re.fullmatch(r"(move|point) (-?[0-9]{1,5}) (-?[0-9]{1,5})", value)
                movement = move is not None
                if movement:
                    action = move[1]
                    dx, dy = int(move[2]), int(move[3])
                    low, high = (-512, 512) if action == "move" else (0, 65535)
                    if not (low <= dx <= high and low <= dy <= high):
                        return 400, "Pointer coordinates out of range."
                elif value not in ("left", "right"):
                    return 400, "Unknown pointer action."
            else:
                return 400, "Unknown input."
            direct_key = kind in ("edit", "typing") or (kind == "text" and len(value) == 1)
            rejected = self.accept_sequence(sequence, movement=movement, editing=direct_key)
            if rejected:
                return rejected
            if not self.execution.acquire(blocking=False):
                return 429, "A macro is running."
            try:
                if kind in ("text", "typing", "edit"):
                    if any(self.pressed(vk) for vk in (0x10, 0x11, 0x12, 0x5B, 0x5C)):
                        return 409, "Release the Windows keyboard modifiers."
                    if kind != "edit":
                        self.write_text(value)
                    else:
                        try:
                            self._keys("tap", EDIT_KEYS[value])
                        finally:
                            self._release_owned()
                elif movement:
                    self.pointer(action, dx, dy)
                else:
                    if self.pressed(1 if value == "left" else 2):
                        return 409, "Release the Windows mouse button."
                    self.pointer(value)
                return 200, "OK"
            except OSError:
                if self.release_error:
                    self._revoke_locked()
                return 503, "Windows could not complete the input. Check the focused app."
            finally:
                self.execution.release()

    def activate_slot(self, token, sequence, revision, profile, slot):
        with self.lock:
            if not self.authorized(token):
                return 403, "Pair on Windows."
            if revision != self.revision:
                return 409, "The profile changed. Refreshing buttons."
            if not 0 <= profile < len(self.profiles) or not 0 <= slot < 9:
                return 404, "Unknown button."
            button = self.profiles[profile]["buttons"][slot]
            if not button:
                return 404, "Empty button."
            rejection = self.accept_sequence(sequence)
            if rejection:
                return rejection
            if not self.execution.acquire(blocking=False):
                return 429, "Another macro is running."
            cancelled = self.cancelled
        try:
            self._release_owned()
            try:
                return self._execute(button, token, cancelled)
            finally:
                self._release_owned()
        except OSError as error:
            if self.release_error:
                super().disable()
            return 503, str(error)
        finally:
            self.execution.release()

    def _execute(self, button, token, cancelled):
        for kind, arg in steps_for(button["steps"]):
            with self.lock:
                if cancelled.is_set() or not self.authorized(token):
                    return 409, "Macro stopped."
                if kind == "launch":
                    self.launch(arg)
                elif kind != "wait":
                    self._keys(kind, arg)
                remaining = self.until - self.clock()
            if kind == "wait":
                delay = arg / 1000
                if cancelled.wait(min(delay, max(0, remaining))) or remaining <= delay:
                    return 409, "Macro stopped."
        return 200, button["label"]

    def _release_owned(self):
        # Preserve ownership if Windows accepts only part of the release batch.
        for _ in range(2):
            if not self.held:
                break
            try:
                sent = self.inject([(key, True) for key in reversed(self.held)])
                if sent:
                    del self.held[-sent:]
            except OSError:
                break
        if self.held:
            self.release_error = "Key release blocked. Focus an ordinary app and click Disable input to retry."
            raise OSError(self.release_error)
        self.release_error = ""

    def _keys(self, kind, keys):
        if kind != "up":
            for key in set(keys).union((0x10, 0x11, 0x12, 0x5B, 0x5C)).difference(self.held):
                if self.pressed(key):
                    raise OSError("Release the keys held on the Windows keyboard.")
        events = []
        if kind != "up":
            events.extend((key, False) for key in keys)
        if kind != "down":
            events.extend((key, True) for key in reversed(keys))
        sent = self.inject(events)
        for key, up in events[:sent]:
            if up:
                self.held.remove(key)
            else:
                self.held.append(key)
        if sent != len(events):
            raise OSError("Windows could not insert the full macro.")

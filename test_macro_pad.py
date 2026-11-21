import http.client
import json
from copy import deepcopy
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

from macro_pad import EXAMPLES, MacroPad, read_profiles, save_profiles, steps_for
from portal import Diagnostic, LocalHTTP
from shortcut_trial import pointer_input, type_text


class MacroTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.apps = []
        self.profiles = read_profiles(EXAMPLES)
        self.pad = MacroPad(self.profiles, self.inject, lambda _: False, self.apps.append)
        self.pair()

    def pair(self):
        pin = self.pad.arm("Macro pad")
        status, self.token = self.pad.pair(pin)
        self.assertEqual(status, 200)

    def inject(self, events):
        self.events.extend(events)
        return len(events)

    def fire(self, slot=0, seq=1):
        return self.pad.activate_slot(self.token, seq, self.pad.revision, 0, slot)[0]

    def test_examples_and_replay(self):
        self.assertEqual(self.fire(), 200)
        self.assertEqual(self.events, [(17, False), (67, False), (67, True), (17, True)])
        self.assertEqual(self.fire(), 409)
        self.assertEqual(self.fire(seq=2), 429)
        self.pair()
        self.assertEqual(self.fire(8), 200)
        self.assertEqual(self.apps, ["notepad"])

    def test_profile_save(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "profiles.json"
            save_profiles(path, self.profiles)
            broken = deepcopy(self.profiles)
            broken[0]["buttons"][0]["steps"] = ["launch arbitrary.exe"]
            with self.assertRaises(ValueError):
                save_profiles(path, broken)
            self.assertEqual(read_profiles(path), self.profiles)
        for steps in (["down Ctrl"], ["up F"], ["wait 3001"], ["tap Ctrl+Ctrl"],
                      ["tap Unknown"], ["tap A"] * 33, ["wait 3000"] * 3):
            with self.subTest(steps=steps), self.assertRaises(ValueError):
                steps_for(steps)

    def test_disable_during_delay_releases_owned_keys(self):
        down = threading.Event()
        def signal(events):
            count = self.inject(events)
            down.set()
            return count
        self.pad.inject = signal
        self.profiles[0]["buttons"][0]["steps"] = ["down Shift", "wait 3000", "tap A", "up Shift"]
        self.pad.set_profiles(self.profiles)
        result = []
        worker = threading.Thread(target=lambda: result.append(self.fire()))
        worker.start()
        try:
            self.assertTrue(down.wait(1))
            self.pad.disable()
        finally:
            worker.join(1)
        self.assertEqual(result, [409])
        self.assertEqual(self.events, [(16, False), (16, True)])
        self.assertEqual(self.fire(seq=2), 403)

    def test_partial_insert_and_physical_key(self):
        batches = []
        def partial_insert(events):
            batches.append(events)
            return 1 if len(batches) == 1 else len(events)
        self.pad.inject = partial_insert
        self.assertEqual(self.fire(), 503)
        self.assertEqual(batches[1], [(17, True)])
        self.pair()
        self.pad.pressed = lambda key: key == 17
        self.assertEqual(self.fire(), 503)
        self.assertEqual(len(batches), 2)

    def test_http_dashboard(self):
        server = LocalHTTP(("127.0.0.1", 0), partial(Diagnostic, run_id="abc", ws_port=0, dashboard=self.pad))
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join)
        self.addCleanup(server.shutdown)
        conn = http.client.HTTPConnection(*server.server_address, timeout=2)
        self.addCleanup(conn.close)
        headers = {"X-Session": self.token, "X-Diagnostic-Run": "abc"}

        def post(path, body):
            conn.request("POST", path, body, headers)
            response = conn.getresponse()
            return response.status, response.read()

        conn.request("GET", "/")
        self.assertIn(b'data-run="abc"', conn.getresponse().read())
        status, body = post("/layout", "layout")
        self.assertEqual(status, 200)
        layout = json.loads(body)
        self.assertNotIn("steps", layout["profiles"][0]["buttons"][0])
        rev = layout["revision"]
        self.assertEqual(post("/macro", f"1 {rev} 1 1")[0], 200)
        self.assertEqual(self.events, [(0xB3, False), (0xB3, True)])
        self.assertEqual(post("/macro", f"2 {rev} 1 8")[0], 404)
        self.assertEqual(post("/macro", f"2 {rev} 0 9")[0], 400)
        self.pad.set_profiles(self.profiles)
        self.assertEqual(post("/macro", f"2 {rev} 0 0")[0], 409)
        self.assertEqual(post("/activate", "3")[0], 404)
        self.pad.disable()
        self.assertEqual(post("/layout", "layout")[0], 403)
        self.assertEqual(post("/text", b"3 should stay private")[0], 403)
        self.assertEqual(post("/pointer", "4 move 1 1")[0], 403)
        self.pair()
        headers["X-Session"] = self.token
        written, pointer = [], []
        self.pad.write_text = written.append
        self.pad.pointer = lambda *args: pointer.append(args)
        text = "  héllo 🎮"
        self.assertEqual(post("/text", ("1 " + text).encode()), (200, b"OK"))
        self.assertEqual(post("/text", ("1 " + text).encode())[0], 409)
        self.assertEqual(post("/text", b"2 bad\nline")[0], 400)
        self.assertEqual(post("/text", b"2 " + b"a" * 257)[0], 400)
        self.assertEqual(post("/text", b"2 \xff")[0], 400)
        self.assertEqual(written, [text])
        self.pad.clock = lambda: self.pad.last_sent + 1
        self.assertEqual(post("/pointer", "2 move -40 21")[0], 200)
        self.assertEqual(post("/pointer", "3 move 1 1")[0], 429)
        self.assertEqual(post("/pointer", "4 move 800 1")[0], 400)
        self.assertEqual(post("/pointer", "5 left")[0], 200)
        self.assertEqual(pointer, [("move", -40, 21), ("left",)])
        self.assertEqual(post("/pointer", "6 point 32768 65535")[0], 200)
        self.assertEqual(pointer[-1], ("point", 32768, 65535))
        self.assertEqual(post("/pointer", "7 point 65536 0")[0], 400)
        self.assertEqual(post("/edit", "8 delete-all")[0], 400)
        self.events.clear()
        self.assertEqual(post("/edit", "8 backspace")[0], 200)
        self.assertEqual(post("/edit", "8 backspace")[0], 409)
        self.assertEqual(post("/edit", "9 backspace")[0], 429)
        self.assertEqual(self.events, [(8, False), (8, True)])
        original_time = self.pad.last_edit
        self.pad.clock = lambda: original_time + 1
        self.assertEqual(post("/edit", "10 alt-tab")[0], 200)
        self.assertEqual(self.events[-4:], [(18, False), (9, False), (9, True), (18, True)])
        current_time = self.pad.last_edit
        self.pad.clock = lambda: current_time + 1
        self.assertEqual(post("/typing", "11  world ")[0], 200)
        self.assertEqual(written[-1], " world ")
        self.assertEqual(post("/typing", "12 " + "a" * 25)[0], 400)
        now = self.pad.last_edit
        self.pad.clock = lambda: now + 1
        self.assertEqual(post("/edit", "13 switch-open")[0], 200)
        self.assertEqual(self.events[-6:], [(17, False), (18, False), (9, False), (9, True), (18, True), (17, True)])
        now += 1
        self.assertEqual(post("/edit", "14 switch-right")[0], 200)
        self.assertEqual(self.events[-2:], [(39, False), (39, True)])
        self.pad.disable()
        self.assertEqual(post("/typing", "15 x")[0], 403)

    def test_windows_input_batches(self):
        keys, mouse = [], []
        def record(items):
            for item in items:
                if item.kind == 1:
                    k = item.data.keyboard
                    keys.append((k.vk, k.scan, k.flags))
                else:
                    m = item.data.mouse
                    mouse.append((m.x, m.y, m.flags))
            return len(items)
        with patch("shortcut_trial.send_inputs", side_effect=record):
            type_text("é🎮")
            pointer_input("move", -14, 20)
            pointer_input("point", 60000, 1555)
            pointer_input("left")
            pointer_input("right")
        self.assertEqual(keys, [(0, unit, flag) for unit in (233, 0xD83C, 0xDFAE) for flag in (4, 6)])
        self.assertEqual(mouse, [(-14, 20, 1), (60000, 1555, 0x8001), (0, 0, 2), (0, 0, 4), (0, 0, 8), (0, 0, 16)])

    def test_partial_click_releases_button(self):
        flags = []
        def partial_click(items):
            flags.append([item.data.mouse.flags for item in items])
            return 1
        with patch("shortcut_trial.send_inputs", side_effect=partial_click), self.assertRaises(OSError):
            pointer_input("right")
        self.assertEqual(flags, [[8, 16], [16]])

    def test_recover_after_windows_blocks_key_release(self):
        counts = iter([1, 0, 0])
        self.pad.inject = lambda events: next(counts)
        self.assertEqual(self.fire(), 503)
        self.assertFalse(self.pad.authorized(self.token))
        self.assertIn("Key release blocked", self.pad.status())
        self.pad.inject = self.inject
        self.pad.disable()
        self.assertEqual(self.events, [(17, True)])
        self.assertEqual(self.pad.status(), "Input disabled")

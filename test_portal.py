import http.client
import socket
import struct
import threading
import unittest
from functools import partial

from portal import Diagnostic, LocalDNS, LocalHTTP, ProbeDNS
from shortcut_trial import ShortcutTrial


def query(name, kind=1):
    labels = b"".join(bytes([len(part)]) + part.encode() for part in name.split("."))
    return struct.pack("!6H", 35, 256, 1, 0, 0, 0) + labels + b"\0" + struct.pack("!HH", kind, 1)


class PortalTests(unittest.TestCase):
    def start(self, server):
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join)
        self.addCleanup(server.shutdown)
        return server.server_address

    def test_dns(self):
        addr = self.start(LocalDNS(("127.0.0.1", 0), ProbeDNS))
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
            client.settimeout(1)
            client.sendto(b"short", addr)
            for name in ("ctest.cdn.nintendo.net", "conntest.nintendowifi.net"):
                client.sendto(query(name), addr)
                reply = client.recv(512)
                self.assertEqual(reply[-4:], socket.inet_aton(addr[0]))
                self.assertEqual(reply[7], 1)
            client.sendto(query(name, 28), addr)
            self.assertEqual(client.recv(512)[7], 0)
            client.sendto(query("example.org"), addr)
            self.assertEqual(client.recv(512)[3] & 15, 5)

    def test_browser_flow(self):
        addr = self.start(LocalHTTP(("127.0.0.1", 0), partial(Diagnostic, run_id="test-run", ws_port=0)))
        conn = http.client.HTTPConnection(*addr, timeout=2)
        self.addCleanup(conn.close)
        conn.request("GET", "/probe", headers={"Host": "conntest.nintendowifi.net"})
        response = conn.getresponse()
        self.assertEqual(response.status, 302)
        self.assertEqual(response.getheader("Location"), f"http://{addr[0]}:{addr[1]}/")
        response.read()
        conn.request("GET", "/")
        self.assertIn(b"test-run", conn.getresponse().read())
        conn.request("GET", "/diagnostic.js")
        self.assertIn(b"XMLHttpRequest", conn.getresponse().read())
        headers = {"X-Diagnostic-Run": "test-run"}
        for body, extra, status in [
            ("tap 1", headers, 200),
            ("ping 1", headers, 200),
            ("tap 0", headers, 400),
            ("tap 1", {}, 403),
            ("tap 1", {**headers, "Origin": "http://example.org"}, 403),
            ("tap 1", {**headers, "Host": "example.org"}, 403),
        ]:
            conn.request("POST", "/echo", body, extra)
            response = conn.getresponse()
            self.assertEqual(response.status, status)
            self.assertEqual(response.read(), body.encode() if status == 200 else b"")

    def test_shortcut_trial(self):
        inserted = []
        clock = [100]
        trial = ShortcutTrial(inserted.append, lambda: clock[0])
        addr = self.start(LocalHTTP(("127.0.0.1", 0), partial(
            Diagnostic, run_id="trial", ws_port=0, trial=trial)))
        conn = http.client.HTTPConnection(*addr, timeout=2)
        self.addCleanup(conn.close)

        def post(path, body, token=""):
            conn.request("POST", path, body, {"X-Diagnostic-Run": "trial", "X-Session": token})
            result = conn.getresponse()
            return result.status, result.read().decode()

        for name in ("Ctrl+F", "Ctrl+A"):
            pin = trial.arm(name)
            self.assertEqual(post("/activate", "1", "0" * 64)[0], 403)
            status, token = post("/pair", pin)
            self.assertEqual(status, 200)
            self.assertEqual(post("/pair", pin)[0], 403)
            self.assertEqual(post("/activate", "1", token)[0], 200)
            self.assertEqual(post("/activate", "1", token)[0], 409)
            self.assertEqual(post("/activate", "2", token)[0], 429)
            trial.disable()
            self.assertEqual(post("/activate", "3", token)[0], 403)
        self.assertEqual(inserted, ["Ctrl+F", "Ctrl+A"])
        pin = trial.arm("Ctrl+F")
        clock[0] += 301
        self.assertEqual(post("/pair", pin)[0], 403)
        pin = trial.arm("Ctrl+F")
        wrong = "000000" if pin != "000000" else "111111"
        for _ in range(5):
            self.assertEqual(post("/pair", wrong)[0], 403)
        self.assertEqual(post("/pair", pin)[0], 403)


if __name__ == "__main__":
    unittest.main()

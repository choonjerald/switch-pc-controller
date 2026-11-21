"""Local Switch Lite diagnostics and an optional paired Windows shortcut trial."""

import argparse
import os
from contextlib import ExitStack
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import IPv4Address, IPv4Network
from pathlib import Path
import re
import secrets
import socket
import socketserver
import struct
from threading import Thread


PROBES = {"conntest.nintendowifi.net", "ctest.cdn.nintendo.net"}
PROBE_LABELS = {name.encode("ascii") for name in PROBES}
WEB = Path(__file__).with_name("web")
PRIVATE = tuple(map(IPv4Network, ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8")))


def local_ip(value):
    address = IPv4Address(value)
    if not any(address in subnet for subnet in PRIVATE):
        raise ValueError("Use the private IPv4 address of your LAN adapter.")
    return str(address)


def address_for_console(client):
    # UDP connect selects a local route without transmitting a datagram.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route:
        route.connect((client, 53))
        return local_ip(route.getsockname()[0])


def dns_reply(packet, address):
    # Only single, uncompressed IN questions. Ignore malformed packets.
    if len(packet) < 17 or len(packet) > 1232:
        return None
    tx, flags, questions, _, _, _ = struct.unpack_from("!6H", packet)
    if flags & 0xF800 or questions != 1:
        return None
    offset = 12
    labels = []
    while offset < len(packet):
        size = packet[offset]
        offset += 1
        if size == 0:
            break
        if size > 63 or offset + size >= len(packet) or offset + size > 266:
            return None
        labels.append(packet[offset:offset + size])
        offset += size
    if offset + 4 > len(packet):
        return None
    qtype, qclass = struct.unpack_from("!HH", packet, offset)
    known = b".".join(labels).lower() in PROBE_LABELS
    has_answer = known and qclass == 1 and qtype == 1
    rcode = 0 if known and qclass == 1 else 5  # REFUSED; never forward.
    header = struct.pack("!6H", tx, 0x8000 | (flags & 0x0100) | rcode, 1, int(has_answer), 0, 0)
    answer = struct.pack("!HHHIH4s", 0xC00C, 1, 1, 0, 4, socket.inet_aton(address)) if has_answer else b""
    return header + packet[12:offset + 4] + answer


class ProbeDNS(socketserver.BaseRequestHandler):
    def handle(self):
        packet, sock = self.request
        reply = dns_reply(packet, self.server.server_address[0])
        if reply:
            sock.sendto(reply, self.client_address)
            if reply[7] == 1:
                print("DNS: console probe answered", flush=True)


class ClientFilter:
    client_ip = None

    def verify_request(self, request, client_address):
        return self.client_ip is None or self.client_ip == client_address[0]


class LocalDNS(ClientFilter, socketserver.UDPServer):
    pass


class LocalHTTP(ClientFilter, ThreadingHTTPServer):
    allow_reuse_address = False


class Diagnostic(BaseHTTPRequestHandler):
    timeout = 4

    def __init__(self, *args, run_id, ws_port, trial=None, dashboard=None, **kwargs):
        self.run_id = run_id
        self.ws_port = ws_port
        self.trial = dashboard or trial
        self.dashboard = dashboard
        super().__init__(*args, **kwargs)

    def log_message(self, *args):
        pass  # Never log arbitrary request paths, headers or bodies.

    @property
    def origin(self):
        address, port = self.server.server_address
        return "http://" + address + ("" if port == 80 else ":" + str(port))

    def send(self, status, body=b"", mime="text/plain", location=None):
        self.send_response(status)
        self.send_header("Content-Type", mime + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if location:
            self.send_header("Location", location)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def host(self):
        return self.headers.get("Host", "").lower()

    def do_GET(self):
        if self.host().split(":")[0] in PROBES:
            print("HTTP: console probe redirected", flush=True)
            return self.send(302, location=self.origin + "/")
        if "http://" + self.host() != self.origin:
            return self.send(403)
        if self.path == "/":
            template = "index.html"
            if self.dashboard:
                template = "dashboard.html"
            elif self.trial:
                template = "shortcut.html"
            page = (WEB / template).read_text(encoding="utf-8")
            page = page.replace("@RUN@", self.run_id).replace("@WS@", str(self.ws_port))
            print("HTTP: diagnostic page requested", flush=True)
            return self.send(200, page.encode(), "text/html")
        if self.path == "/diagnostic.js":
            return self.send(200, (WEB / "diagnostic.js").read_bytes(), "application/javascript")
        if self.dashboard and self.path in ("/dashboard.js", "/desktop_controls.js"):
            return self.send(200, (WEB / self.path[1:]).read_bytes(), "application/javascript")
        return self.send(404)

    do_HEAD = do_GET

    def do_POST(self):
        routes = {"/echo"}
        if self.trial:
            routes.add("/pair")
            routes.update(("/layout", "/macro", "/pointer", "/text", "/typing", "/edit") if self.dashboard else ("/activate",))
        if self.path not in routes:
            return self.send(404)
        if "http://" + self.host() != self.origin or self.headers.get("Origin", self.origin) != self.origin:
            return self.send(403)
        if self.headers.get("X-Diagnostic-Run") != self.run_id:
            return self.send(403)
        length = self.headers.get("Content-Length", "")
        limit = {"/text": 1034, "/typing": 106}.get(self.path, 32)
        if not re.fullmatch(r"[1-9][0-9]{0,3}", length) or int(length) > limit:
            return self.send(400)
        body = self.rfile.read(int(length))
        if self.path == "/pair":
            if not re.fullmatch(rb"[0-9]{6}", body):
                return self.send(400)
            status, message = self.trial.pair(body.decode("ascii"))
            return self.send(status, message.encode())
        if self.path in ("/activate", "/macro", "/layout", "/pointer", "/text", "/typing", "/edit"):
            token = self.headers.get("X-Session", "")
            if not re.fullmatch("[0-9a-f]{64}", token):
                return self.send(403)
            if self.path in ("/pointer", "/text", "/typing", "/edit"):
                seq, separator, raw = body.partition(b" ")
                if not separator or not re.fullmatch(rb"[1-9][0-9]{0,8}", seq):
                    return self.send(400)
                try:
                    value = raw.decode("utf-8")
                except UnicodeDecodeError:
                    return self.send(400)
                status, message = self.dashboard.desktop_input(token, int(seq), self.path[1:], value)
                return self.send(status, message.encode())
            if self.path == "/layout":
                if body != b"layout":
                    return self.send(400)
                status, message = self.dashboard.get_layout(token)
                return self.send(status, message.encode(), "application/json" if status == 200 else "text/plain")
            if self.path == "/macro":
                match = re.fullmatch(rb"([1-9][0-9]{0,8}) ([0-9a-f]{8}) ([0-9]{1,2}) ([0-8])", body)
                if not match:
                    return self.send(400)
                sequence, revision, profile, slot = match.groups()
                status, message = self.dashboard.activate_slot(
                    token, int(sequence), revision.decode("ascii"), int(profile), int(slot))
                return self.send(status, message.encode())
            if not re.fullmatch(rb"[1-9][0-9]{0,8}", body):
                return self.send(400)
            status, message = self.trial.activate(token, int(body))
            return self.send(status, message.encode())
        if not re.fullmatch(rb"(tap|ping) [1-9][0-9]{0,8}", body):
            return self.send(400)
        if body.startswith(b"tap"):
            print("PC acknowledged " + body.decode("ascii"), flush=True)
        self.send(200, body)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", type=local_ip, help="override automatic selection of the PC's LAN IPv4")
    parser.add_argument("--client", required=True, type=local_ip, help="only accept this console's IPv4")
    parser.add_argument("--ws", action="store_true", help="enable optional WebSocket echo on TCP 8765")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--shortcut-trial", action="store_true", help="show the Windows pairing and shortcut controls")
    mode.add_argument("--dashboard", action="store_true", help="open the macro pad and local profile editor")
    parser.add_argument("--profiles", type=Path, help="dashboard profile JSON file")
    args = parser.parse_args(argv)
    if args.profiles and not args.dashboard:
        parser.error("--profiles requires --dashboard")
    if not args.bind:
        args.bind = address_for_console(args.client)
    run_id = secrets.token_hex(4)
    origin = "http://" + args.bind
    with ExitStack() as stack:
        trial = dashboard = None
        if args.shortcut_trial:
            from shortcut_trial import ShortcutTrial, show_controls
            trial = ShortcutTrial()
        if args.dashboard:
            from macro_pad import EXAMPLES, MacroPad, read_profiles
            from profile_editor import show_editor
            config = args.profiles or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "SwitchPCController" / "profiles.json"
            dashboard = MacroPad(read_profiles(config if config.exists() or args.profiles else EXAMPLES))
        handler = partial(Diagnostic, run_id=run_id, ws_port=8765 if args.ws else 0, trial=trial, dashboard=dashboard)
        http = stack.enter_context(LocalHTTP((args.bind, 80), handler))
        dns = stack.enter_context(LocalDNS((args.bind, 53), ProbeDNS))
        http.client_ip = dns.client_ip = args.client
        if args.ws:
            from websockets.sync.server import serve

            def echo(connection):
                with connection:
                    if args.client and connection.remote_address[0] != args.client:
                        return
                    if connection.request.path == "/echo" and connection.recv(timeout=4) == "ping":
                        connection.send("pong")

            ws = stack.enter_context(serve(echo, args.bind, 8765, origins=[origin], max_size=32))
            Thread(target=ws.serve_forever, daemon=True).start()
            stack.callback(ws.shutdown)
        Thread(target=dns.serve_forever, daemon=True).start()
        stack.callback(dns.shutdown)
        print(f"Run {run_id} | {origin}/ | Switch DNS {args.bind} | Ctrl+C to stop", flush=True)
        print(f"Allowed console: {args.client}", flush=True)
        firewall = f".\\firewall.ps1 -PcAddress {args.bind} -SwitchAddress {args.client}"
        print("If Windows blocks the connection, run in administrator PowerShell:", flush=True)
        print(firewall + (" -WebSocket" if args.ws else ""), flush=True)
        if trial or dashboard:
            Thread(target=http.serve_forever, daemon=True).start()
            stack.callback(http.shutdown)
            if dashboard:
                try:
                    show_editor(dashboard, config)
                finally:
                    dashboard.disable()
            else:
                show_controls(trial)
        else:
            http.serve_forever()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError, ImportError) as exc:
        raise SystemExit(f"Portal could not start: {exc}")

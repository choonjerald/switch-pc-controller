"""Friendly launcher for the Windows dashboard."""

import argparse
import os
from pathlib import Path

from portal import local_ip, main as run_portal

SAVED = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "SwitchPCController" / "switch_ip.txt"


def saved_ip():
    try:
        return local_ip(SAVED.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def save_ip(client):
    try:
        SAVED.parent.mkdir(parents=True, exist_ok=True)
        SAVED.write_text(client + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"Could not remember the Switch IP address: {exc}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", help="Switch IP address. Defaults to the saved address if available.")
    args = parser.parse_args()
    previous = saved_ip()
    if args.client is not None:
        try:
            client = local_ip(args.client)
        except ValueError as exc:
            parser.error(str(exc))
    elif previous is not None:
        client = previous
    else:
        print("Switch PC Controller")
        print("On the Switch, open System Settings > Internet and find IP Address.")
        while True:
            try:
                client = local_ip(input("Switch IP address: ").strip())
                break
            except ValueError:
                print("Enter the Switch's private IPv4 address, such as 192.168.1.50.")
    if client != previous:
        save_ip(client)
    run_portal(["--client", client, "--dashboard"])


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        pass
    except (OSError, ValueError, ImportError) as exc:
        raise SystemExit(f"Could not start Switch PC Controller: {exc}")

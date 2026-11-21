"""Friendly launcher for the Windows dashboard."""

import argparse

from portal import local_ip, main as run_portal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", help="Switch IP address. Omit to enter it interactively.")
    args = parser.parse_args()
    if not args.client:
        print("Switch PC Controller")
        print("On the Switch, open System Settings > Internet and find IP Address.")
    address = args.client
    while True:
        try:
            client = local_ip(address or input("Switch IP address: ").strip())
            break
        except ValueError as exc:
            if address:
                parser.error(str(exc))
            print("Enter the Switch's private IPv4 address, such as 192.168.1.50.")
    run_portal(["--client", client, "--dashboard"])


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        pass
    except (OSError, ValueError, ImportError) as exc:
        raise SystemExit(f"Could not start Switch PC Controller: {exc}")

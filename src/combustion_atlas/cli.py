"""Top-level convenience command."""

from __future__ import annotations

import argparse

from .setup.doctor import main as doctor_main


def main() -> int:
    parser = argparse.ArgumentParser(description="Combustion Atlas command line")
    parser.add_argument("command", choices=["doctor"])
    args = parser.parse_args()
    if args.command == "doctor":
        return doctor_main()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

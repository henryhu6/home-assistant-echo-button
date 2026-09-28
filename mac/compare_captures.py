"""Compare two private Echo Button captures without printing device IDs.

Byte 27 of the 32-byte startup message appears to be battery percentage based
on a controlled AAA replacement. This tool shows the raw comparison evidence.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from echo_button_protocol import battery_percent


def frames(path: Path) -> list[bytes]:
    """Read callback buffers from a local capture file."""
    return [
        bytes.fromhex(line.split(": ", 1)[1])
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith("RX ")
    ]


def first_of_length(capture: list[bytes], length: int) -> bytes | None:
    return next((frame for frame in capture if len(frame) == length), None)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    args = parser.parse_args()
    before = frames(args.before)
    after = frames(args.after)
    print("Buffer lengths before:", [len(frame) for frame in before])
    print("Buffer lengths after: ", [len(frame) for frame in after])
    for length in (54, 32, 40):
        old = first_of_length(before, length)
        new = first_of_length(after, length)
        if old is None or new is None:
            print(f"{length}-byte frame missing from one capture")
            continue
        changed = [
            (offset, old[offset], new[offset])
            for offset in range(length)
            if old[offset] != new[offset]
            and offset not in range(8, 24)  # Device identifier
        ]
        print(f"{length}-byte changed offsets, excluding device ID: {changed}")
        if length == 32:
            print(
                "32-byte startup battery report: "
                f"{battery_percent(old)}% -> {battery_percent(new)}% "
                "(experimental)"
            )


if __name__ == "__main__":
    main()

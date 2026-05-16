#!/usr/bin/env python3
"""
Generate synthetic J1939 candump fixture for performance benchmarking.

Usage:
    python3 scripts/generate_benchmark_fixture.py --count 10000 --output tests/fixtures/j1939_large_benchmark.candump
"""

import argparse
import random
import sys
from pathlib import Path


def generate_j1939_frame(
    timestamp: float, interface: str, pgn: int, sa: int, da: int, data: bytes
) -> str:
    priority = random.choice([0, 3, 6, 7])
    pgn_data = pgn << 8
    id_val = (priority << 26) | (pgn_data) | (da << 8) | sa
    id_hex = f"{id_val:08X}"
    data_hex = data.hex().upper()
    return f"({timestamp:.6f}) {interface} {id_hex}#{data_hex}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate synthetic J1939 candump benchmark fixture"
    )
    parser.add_argument("--count", type=int, default=10000, help="Number of frames to generate")
    parser.add_argument("--output", type=str, required=True, help="Output file path")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    args = parser.parse_args()

    random.seed(args.seed)

    interfaces = ["can0", "can1", "can2"]
    pgns = [65262, 61444, 65259, 65226, 60928, 65184, 65103]
    source_addresses = [0x00, 0x10, 0x20, 0x31, 0x40, 0x50, 0xF4, 0xFF]

    timestamp = 0.0
    output = []

    for i in range(args.count):
        pgn = random.choice(pgns)
        sa = random.choice(source_addresses)
        da = random.choice([255] + source_addresses[:3])
        data = bytes([random.randint(0, 255) for _ in range(random.choice([8, 8, 8, 4, 2]))])
        interface = random.choice(interfaces)

        output.append(generate_j1939_frame(timestamp, interface, pgn, sa, da, data))
        timestamp += random.uniform(0.001, 0.01)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w") as f:
        f.write("\n".join(output))

    print(f"Generated {args.count} frame benchmark fixture: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

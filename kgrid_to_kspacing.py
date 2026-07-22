#!/usr/bin/env python3
"""Convert an explicit VASP k-point grid to a suitable KSPACING value."""

from __future__ import annotations

import argparse
import sys
from math import inf
from pathlib import Path


def positive_integer(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("k-grid values must be positive integers")
    return number


def kspacing_interval(
    reciprocal_lengths: tuple[float, float, float],
    kgrid: tuple[int, int, int],
) -> tuple[float, float, tuple[float, float, float]]:
    """Return the KSPACING interval that reproduces an explicit grid."""
    directional = tuple(length / points for length, points in zip(reciprocal_lengths, kgrid))
    lower = max(directional)
    upper = min(
        length / (points - 1) if points > 1 else inf
        for length, points in zip(reciprocal_lengths, kgrid)
    )
    return lower, upper, directional


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("structure", help="POSCAR, CONTCAR, CIF, or another pymatgen structure file")
    parser.add_argument(
        "kgrid",
        nargs=3,
        type=positive_integer,
        metavar="N",
        help="converged k-point grid, for example 6 6 4",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    structure_path = Path(args.structure).expanduser().resolve()
    if not structure_path.is_file():
        print(f"ERROR: structure file not found: {structure_path}", file=sys.stderr)
        return 2

    try:
        from pymatgen.core import Structure

        structure = Structure.from_file(structure_path)
    except (ImportError, ValueError, OSError) as exc:
        print(f"ERROR: could not read {structure_path}: {exc}", file=sys.stderr)
        return 2

    kgrid = tuple(args.kgrid)
    reciprocal_lengths = tuple(float(value) for value in structure.lattice.reciprocal_lattice.abc)
    lower, upper, directional = kspacing_interval(reciprocal_lengths, kgrid)

    print(f"Structure: {structure_path}")
    print(f"K-grid: {kgrid[0]} x {kgrid[1]} x {kgrid[2]}")
    print("Reciprocal lengths (1/Angstrom): " + " ".join(f"{value:.6f}" for value in reciprocal_lengths))
    print("Directional spacings (1/Angstrom): " + " ".join(f"{value:.6f}" for value in directional))

    if lower < upper:
        kspacing = (lower + upper) / 2
        print(f"Exact-grid interval: {lower:.6f} <= KSPACING < {upper:.6f}")
        print(f"Recommended KSPACING: {kspacing:.6f}")
    else:
        conservative = min(directional)
        print("No single KSPACING reproduces this exact anisotropic grid.")
        print(f"Conservative KSPACING: {conservative:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

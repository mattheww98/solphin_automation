#!/usr/bin/env python3
"""Analyse completed Solphin VASP calculations and write a JSON summary."""

from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt
import numpy as np

from workflow_common import WorkflowError, json_number, load_config, require_file


@contextmanager
def working_directory(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def solphin_modules():
    try:
        from solphin import band_structure, db_fom, dos, final_results, optics, spectral
    except (ImportError, ModuleNotFoundError) as exc:
        raise WorkflowError(
            "Solphin and its dependencies are not importable. Activate the Solphin environment. "
            f"Original error: {exc}"
        ) from exc
    return band_structure, db_fom, dos, final_results, optics, spectral


def analyse(config: dict, root: Path) -> Path:
    band_structure, db_fom, dos, final_results, optics, spectral = solphin_modules()
    optics_dir = root / config["optics"]["directory"]
    bands_dir = root / config["bands"]["directory"]
    result_dir = root / config["analysis"]["directory"]
    result_dir.mkdir(parents=True, exist_ok=True)
    optics_vasprun = require_file(optics_dir / "vasprun.xml", "completed optics vasprun.xml")

    bs = band_structure.get_band_structure(str(bands_dir), int(config["bands"]["splits"]))
    gap_info = bs.get_band_gap()
    fundamental_gap = float(gap_info["energy"])
    direct_gap = float(bs.get_direct_band_gap())

    fig, _ = plt.subplots(figsize=(5, 4), dpi=180)
    band_structure.plot_band_structure(bs, plt, ymin=-6, ymax=6)
    plt.savefig(result_dir / "band_structure.pdf", bbox_inches="tight")
    plt.close("all")

    eps_inf, eps_tensor, eps_full, _, energies = optics.calc_dielectric(str(optics_vasprun))
    optical_data = optics.calc_absorption(eps_full, energies)
    np.savetxt(
        optics_dir / "absorption.dat",
        np.column_stack((energies, optical_data["absorption"] / 100.0)),
        header="energy(eV) absorption(cm^-1)",
    )
    np.savetxt(
        optics_dir / "n_real.dat",
        np.column_stack((energies, optical_data["n_real"])),
        header="energy(eV) n_real",
    )
    fig, ax = plt.subplots(figsize=(5, 3), dpi=180)
    ax.plot(energies, optical_data["absorption"] / 100.0)
    ax.set(xlabel="Energy (eV)", ylabel=r"Absorption (cm$^{-1}$)", xlim=(0, 6))
    fig.tight_layout()
    fig.savefig(result_dir / "absorption.pdf")
    plt.close(fig)

    analysis = config["analysis"]
    computed_dos = dos.compute_dos(
        dos_vasprun=str(optics_vasprun),
        bs_directory=str(bands_dir),
        sigma=float(analysis["dos_gaussian"]),
        carrier=analysis["dos_carrier"],
    )
    dos_mass = json_number(computed_dos.final_result)
    with working_directory(result_dir):
        dos.plot_dos(str(optics_vasprun), gaussian=float(analysis["dos_gaussian"]), save=True)
    plt.close("all")

    spectrum = db_fom.load_spectrum(analysis["spectrum"])
    photon_spectrum = db_fom.convert_spectrum(spectrum)
    spectral_average, spectral_dispersion = spectral.generate_spectral_parameters(
        str(optics_dir), spectrum, E_gap=fundamental_gap
    )
    optics.make_blank_plot(
        str(optics_dir),
        direct_gap=direct_gap,
        indirect_gap=fundamental_gap,
        spectrum_type=analysis["spectrum"],
        Qi=float(analysis["blank_qi"]),
        n=float(analysis["blank_refractive_index"]),
    )
    plt.savefig(result_dir / "efficiency_vs_thickness.pdf", bbox_inches="tight")
    plt.close("all")

    sq, fom_sq, efficiency, fom = final_results.SQ_relative_FOM_PV_efficiency(
        fundamental_gap,
        photon_spectrum,
        float(spectral_average),
        float(analysis["carrier_lifetime"]),
        float(spectral_dispersion),
        float(dos_mass),
        float(analysis["dopant_density"]),
        float(eps_inf),
        float(analysis["carrier_mobility"]),
        float(analysis["cell_temperature"]),
    )
    summary = {
        "band_gap_eV": fundamental_gap,
        "direct_band_gap_eV": direct_gap,
        "band_gap_transition": gap_info.get("transition"),
        "epsilon_infinity": float(eps_inf),
        "epsilon_infinity_tensor": np.asarray(eps_tensor).tolist(),
        "dos_effective_mass_m0": dos_mass,
        "spectral_average_cm-1": float(spectral_average),
        "spectral_dispersion": float(spectral_dispersion),
        "shockley_queisser_limit_percent": float(sq),
        "fom_relative_to_sq_percent": float(fom_sq),
        "fom_efficiency_percent": float(efficiency),
        "photovoltaic_fom": float(fom),
    }
    output = result_dir / "summary.json"
    output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", help="workflow config.json")
    args = parser.parse_args()
    try:
        config, _, root = load_config(args.config)
        output = analyse(config, root)
        print(f"WROTE analysis summary: {output}")
        return 0
    except (WorkflowError, FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import prepare_workflow
import analyse_workflow
from workflow_common import WorkflowError, load_config


class FakeVaspInputs:
    @staticmethod
    def read_structure_pmg(filename):
        return {"structure": str(filename)}

    @staticmethod
    def write_vasp_calculation(structure, recipe, out_dir, patches, **kwargs):
        directory = Path(out_dir)
        directory.mkdir(parents=True, exist_ok=True)
        settings = kwargs["user_incar_settings"]
        incar = "".join(f"{key} = {value}\n" for key, value in settings.items())
        (directory / "INCAR").write_text(incar, encoding="utf-8")
        (directory / "POSCAR").write_text("fake POSCAR\n", encoding="utf-8")
        (directory / "POTCAR").write_text("fake POTCAR\n", encoding="utf-8")


class FakeBands:
    class Kpoints:
        @staticmethod
        def from_file(filename):
            return object()

    @staticmethod
    def generate_band_structure_path(**kwargs):
        return kwargs["structure"], ([(0, 0, 0)], ["G"])

    @staticmethod
    def _write_kpoint_files(directory, make_folders, kpts_per_split, **kwargs):
        root = Path(directory)
        folders = ["split-01", "split-02"] if make_folders else [""]
        for folder in folders:
            target = root / folder
            target.mkdir(parents=True, exist_ok=True)
            (target / "KPOINTS").write_text("fake KPOINTS\n", encoding="utf-8")
        return folders

    @staticmethod
    def get_band_structure(directory, splits):
        class BandStructure:
            @staticmethod
            def get_band_gap():
                return {"energy": 1.5, "transition": "G-G"}

            @staticmethod
            def get_direct_band_gap():
                return 1.6

        return BandStructure()

    @staticmethod
    def plot_band_structure(bs, plt, **kwargs):
        plt.plot([0, 1], [0, 1])


class FakeOptics:
    @staticmethod
    def calc_dielectric(filename):
        energies = np.array([0.0, 1.0, 2.0])
        eps = np.tile(np.eye(3, dtype=complex), (3, 1, 1)) * 4
        return 4.0, np.eye(3) * 4, eps, eps.imag, energies

    @staticmethod
    def calc_absorption(eps, energies):
        return {"absorption": np.array([0.0, 1.0e5, 2.0e5]), "n_real": np.full(3, 2.0)}

    @staticmethod
    def make_blank_plot(*args, **kwargs):
        analyse_workflow.plt.figure()
        analyse_workflow.plt.plot([1, 2], [10, 20])


class FakeDos:
    @staticmethod
    def compute_dos(**kwargs):
        return type("DOSResult", (), {"final_result": 0.25})()

    @staticmethod
    def plot_dos(filename, **kwargs):
        analyse_workflow.plt.figure()
        analyse_workflow.plt.plot([0, 1], [1, 0])
        if kwargs.get("save"):
            analyse_workflow.plt.savefig("dos.pdf")


class FakeDb:
    @staticmethod
    def load_spectrum(name):
        return np.array([[400.0, 1.0], [800.0, 0.5]])

    @staticmethod
    def convert_spectrum(spectrum):
        return spectrum


class FakeSpectral:
    @staticmethod
    def generate_spectral_parameters(*args, **kwargs):
        return 10000.0, 0.5


class FakeFinal:
    @staticmethod
    def SQ_relative_FOM_PV_efficiency(*args):
        return 30.0, 80.0, 24.0, 1.2


class WorkflowTests(unittest.TestCase):
    def make_config(self, directory: Path, overrides=None):
        data = {"project_name": "test", "workdir": "work"}
        if overrides:
            data.update(overrides)
        path = directory / "config.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return load_config(path)

    def test_config_paths_are_relative_to_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, config_path, root = self.make_config(Path(tmp))
            self.assertEqual(root, config_path.parent / "work")

    def test_real_vaspup_generates_convergence_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            config, config_path, root = self.make_config(
                Path(tmp),
                {
                    "convergence": {
                        "encut": {"start": 300, "stop": 350, "step": 50},
                        "kpoints": [[2, 2, 2], [3, 3, 3]],
                    }
                },
            )
            root.mkdir()
            with patch.object(
                prepare_workflow,
                "solphin_modules",
                return_value=(FakeBands, FakeVaspInputs),
            ), patch.object(
                FakeVaspInputs,
                "write_vasp_calculation",
                wraps=FakeVaspInputs.write_vasp_calculation,
            ) as writer:
                prepare_workflow.prepare_convergence({}, config, config_path, root)

            convergence = root / "convergence"
            self.assertEqual(writer.call_args.kwargs["recipe"], "PBEsol")
            self.assertTrue((convergence / "cutoff_converge/e300/INCAR").is_file())
            self.assertTrue((convergence / "cutoff_converge/e350/INCAR").is_file())
            self.assertTrue((convergence / "kpoint_converge/k2,2,2/KPOINTS").is_file())
            self.assertIn("ENCUT  = 350 eV", (convergence / "cutoff_converge/e350/INCAR").read_text())
            self.assertEqual(
                (convergence / "kpoint_converge/k3,3,3/KPOINTS").read_text().splitlines()[3],
                "3 3 3",
            )
            self.assertNotIn("KSPACING", (convergence / "input/INCAR").read_text())

    def test_relax_optics_and_split_bands_follow_prerequisites(self):
        with tempfile.TemporaryDirectory() as tmp:
            config, config_path, root = self.make_config(
                Path(tmp), {"bands": {"splits": 2, "functional": "PBEsol"}}
            )
            root.mkdir()
            with patch.object(
                prepare_workflow,
                "solphin_modules",
                return_value=(FakeBands, FakeVaspInputs),
            ):
                prepare_workflow.prepare_relax({}, config, config_path, root)
                with self.assertRaises(WorkflowError):
                    prepare_workflow.prepare_optics(config, config_path, root)
                (root / "relax/CONTCAR").write_text("relaxed\n", encoding="utf-8")
                prepare_workflow.prepare_optics(config, config_path, root)
                with self.assertRaises(WorkflowError):
                    prepare_workflow.prepare_bands(config, config_path, root)
                (root / "optics/CHGCAR").write_text("charge\n", encoding="utf-8")
                prepare_workflow.prepare_bands(config, config_path, root)

            self.assertTrue((root / "bands/split-01/INCAR").is_file())
            self.assertTrue((root / "bands/split-02/INCAR").is_file())

    def test_analysis_writes_summary_and_plots(self):
        with tempfile.TemporaryDirectory() as tmp:
            config, _, root = self.make_config(Path(tmp))
            (root / "optics").mkdir(parents=True)
            (root / "optics/vasprun.xml").write_text("fake\n", encoding="utf-8")
            modules = (FakeBands, FakeDb, FakeDos, FakeFinal, FakeOptics, FakeSpectral)
            with patch.object(analyse_workflow, "solphin_modules", return_value=modules):
                summary_path = analyse_workflow.analyse(config, root)

            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["band_gap_eV"], 1.5)
            self.assertEqual(summary["fom_efficiency_percent"], 24.0)
            for name in ("absorption.pdf", "band_structure.pdf", "dos.pdf", "efficiency_vs_thickness.pdf"):
                self.assertTrue((root / "results" / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()

"""Shared configuration and filesystem helpers for the Solphin workflow."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


DEFAULTS: dict[str, Any] = {
    "project_name": "material",
    "workdir": ".",
    "functional": "HSE06",
    "encut": 450,
    "kspacing": 0.2,
    "potcar_functional": "PBE_54",
    "incar": {},
    "scheduler": {"job_template": None, "job_filename": "job"},
    "convergence": {
        "enabled": True,
        "functional": "PBEsol",
        "parameters_confirmed": False,
        "generate_directories": True,
        "run_vasp": False,
        "command": "generate-converge",
        "encut": {"enabled": True, "start": 300, "stop": 700, "step": 50},
        "kpoints": [[3, 3, 3], [4, 4, 4], [5, 5, 5], [6, 6, 6]],
        "seed_kpoints": [1, 1, 1],
        "incar": {"ISPIN": 1, "ISMEAR": 0, "SIGMA": 0.05},
    },
    "relax": {"directory": "relax", "patches": ["relax_cell", "tight_relax"], "incar": {}},
    "optics": {
        "directory": "optics",
        "patches": ["optics"],
        "incar": {"ISPIN": 1, "ISMEAR": -5, "SIGMA": 0.02, "LORBIT": 14},
    },
    "bands": {
        "directory": "bands",
        "functional": "PBEsol",
        "splits": 1,
        "path_definition": "bradcrack",
        "path_density": 60,
        "patches": [],
        "incar": {},
    },
    "analysis": {
        "directory": "results",
        "spectrum": "AM1.5",
        "cell_temperature": 300.0,
        "carrier_lifetime": 2.5e-7,
        "carrier_mobility": 10.0,
        "dopant_density": 1.0e16,
        "dos_carrier": "electrons",
        "dos_gaussian": 0.05,
        "blank_qi": 1.0,
        "blank_refractive_index": 3.5,
    },
}


class WorkflowError(RuntimeError):
    """A user-actionable workflow setup error."""


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(filename: str | Path) -> tuple[dict[str, Any], Path, Path]:
    path = Path(filename).expanduser().resolve()
    if not path.is_file():
        raise WorkflowError(f"Configuration file not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise WorkflowError(f"Could not read {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise WorkflowError("The top level of config.json must be a JSON object.")
    config = _merge(DEFAULTS, raw)
    root = Path(config["workdir"]).expanduser()
    if not root.is_absolute():
        root = path.parent / root
    root = root.resolve()
    return config, path, root


def stage_settings(config: dict[str, Any], stage: str) -> dict[str, Any]:
    """Merge common INCAR settings with settings specific to one stage."""
    return _merge(config.get("incar", {}), config[stage].get("incar", {}))


def resolve_config_path(value: str | None, config_path: Path) -> Path | None:
    if value is None:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = config_path.parent / path
    return path.resolve()


def require_file(path: Path, purpose: str) -> Path:
    if not path.is_file():
        raise WorkflowError(f"{purpose} is not available yet: {path}")
    return path


def target_is_prepared(directory: Path) -> bool:
    return all((directory / name).is_file() for name in ("INCAR", "POSCAR", "POTCAR"))


def ensure_new_target(directory: Path, allowed_files: set[str] | None = None) -> None:
    if target_is_prepared(directory):
        raise WorkflowError(f"already prepared: {directory}")
    existing = {path.name for path in directory.iterdir()} if directory.exists() else set()
    if existing - (allowed_files or set()):
        raise WorkflowError(
            f"Refusing to overwrite the non-empty, incomplete directory: {directory}"
        )


def copy_job(config: dict[str, Any], config_path: Path, directories: list[Path]) -> None:
    scheduler = config["scheduler"]
    filename = scheduler.get("job_filename", "job")
    configured_template = scheduler.get("job_template")
    if configured_template is None:
        # Convenient default: discover a batch script kept beside config.json.
        template = config_path.parent / filename
        if not template.is_file():
            return
    else:
        template = resolve_config_path(configured_template, config_path)
        require_file(template, "scheduler.job_template")
    for directory in directories:
        shutil.copy2(template, directory / filename)


def find_command(command: str) -> str:
    """Find a vaspup command on PATH, with the user's source checkout as fallback."""
    found = shutil.which(command)
    if found:
        return found
    fallback = Path.home() / "src" / "vaspup2.0" / "bin" / command
    if fallback.is_file():
        return str(fallback)
    raise WorkflowError(
        f"Could not find '{command}' on PATH or at {fallback}. "
        "Add vaspup2.0/bin to PATH or set convergence.command."
    )


def json_number(value: Any) -> float | None:
    """Turn numpy-like scalar values into JSON-safe floats."""
    if value is None:
        return None
    return float(value)

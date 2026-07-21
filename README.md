# Solphin automation

This directory turns the workflow in `~/src/solphin/tutorial/full_workflow_tutorial.ipynb`
into two command-line scripts. A POSCAR or CIF plus a JSON file are the only initial inputs.

The calculation sequence is:

1. `vaspup2.0` ENCUT and k-mesh convergence calculations
2. cell relaxation
3. combined optics and density-of-states calculation
4. GGA or hybrid band structure calculation
5. Solphin analysis (gaps, dielectric response, absorption, DOS mass, spectral
   parameters, SLME/Blank plot, and photovoltaic FoM)

## Environment

Activate the `vasp` conda environment, which has been verified with Solphin using
`pymatgen 2025.10.7`, `sumo 2.3.8`, `scipy 1.17.1`, and `matplotlib 3.11.1`.
Solphin also requires VASP pseudopotentials configured through `PMG_VASP_PSP_DIR`, as
described in `~/src/solphin/README.md`.

For example, from an appropriate environment:

```bash
conda activate vasp
python -m pip install --no-deps -e ~/src/solphin
```

Use `--no-deps` for subsequent editable reinstalls: unbounded dependency resolution can
select the split pymatgen 2026 package, which is incompatible with sumo 2.3.8.

`prepare_workflow.py` first looks for the configured vaspup command on `PATH`, then falls
back to `~/src/vaspup2.0/bin/generate-converge`.

## Configure

Copy `config.example.json`, set `workdir`, and adjust the calculation settings. In
particular:

- set `scheduler.job_template` to a batch script if you want it copied into every calculation;
- the example uses `PBE_54`, matching the potentials currently installed under
  `~/src/pmg_potcars/POT_GGA_PAW_PBE_54`;
- keep `convergence.run_vasp` false to generate without submitting;
- set it true only after providing a job template and the correct `submit_cmd` and
  `job_name_flag`;
- after inspecting convergence results, update the production `encut` and `kspacing`, then
  set `convergence.parameters_confirmed` to `true`.

`job_template` and a relative `workdir` are resolved relative to the JSON file.

## Prepare and advance the workflow

```bash
cd ~/solphin_automation
cp config.example.json config.json
python prepare_workflow.py /path/to/POSCAR config.json
```

The default `--stage auto` is safe to rerun. Initially it prepares convergence inputs and
waits. After the convergence jobs finish, run `data-converge`, update the production
`encut`/`kspacing`, set `convergence.parameters_confirmed` to `true`, and rerun the same
command to prepare relaxation:

```bash
python prepare_workflow.py /path/to/POSCAR config.json
```

Once `relax/CONTCAR` exists it prepares optics. Once the optics calculation supplies
`CHGCAR` (GGA bands) or `IBZKPT` (hybrid bands), it prepares the band calculation.
Prepared stages are skipped; non-empty incomplete directories are never overwritten.

To prepare only one stage, use one of:

```bash
python prepare_workflow.py structure.cif config.json --stage convergence
python prepare_workflow.py structure.cif config.json --stage relax
python prepare_workflow.py structure.cif config.json --stage optics
python prepare_workflow.py structure.cif config.json --stage bands
```

Run `data-converge` separately inside `convergence/cutoff_converge` and
`convergence/kpoint_converge` after those VASP jobs complete, as required by vaspup2.0.

## Analyse completed calculations

After optics and all band calculations have completed:

```bash
python analyse_workflow.py config.json
```

The analysis directory contains `summary.json`, `absorption.pdf`, `dos.pdf`,
`band_structure.pdf`, and `efficiency_vs_thickness.pdf`. It also writes the derived
`absorption.dat` and `n_real.dat` alongside the optics output.

## Notes

- Solphin's `relax_cell` patch increases the requested ENCUT by 30%, matching the notebook.
- The example uses HSE06 for relaxation/optics and PBEsol for a one-piece band calculation,
  also matching the tutorial's active code path.
- For hybrid bands, choose `HSE06` or `PBE0` under `bands.functional`, set a useful number
  of `bands.splits`, and ensure the optics run has produced `IBZKPT`.

# Stage 2 Execution Selection and Workspace Repair

Date: 2026-08-19

Before confirmatory execution, an integration audit found that three experimental harness drafts had been written against incompatible versions of `stage2_research.py`. No confirmatory Stage 2 dataset had been produced. The incompatible files were preserved under `archive/stage2_workspace_repair_20260819/` with SHA-256 hashes.

The executable research cycle selected for confirmation is **Stage 2 Cycle 1**, governed by `docs/stage2_cycle1_preregistered_protocol.md`. It has a coherent implementation in:

- `src/fleet_sim/security/attack_operator.py`
- `src/fleet_sim/analysis/admission_stability.py`
- `src/fleet_sim/experiments/stage2_research.py`
- `scripts/run_stage2_cycle1.py`

The broader `stage2_preregistered_protocol.md` and the later Cycle 3 draft remain preserved as unexecuted protocols. They must not be represented as governing the Cycle 1 dataset. Any future execution of either requires a compatible code manifest and a separate result directory.

The repair changed only test and runner compatibility. It did not alter the Cycle 1 equations, experimental matrix, splits, acceptance criteria, or primary seed.

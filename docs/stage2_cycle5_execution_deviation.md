# Stage 2 Cycle 5 Execution Deviation Record

Date: 2026-08-19

Two initial execution attempts ended before writing any simulation artifact. The first detached process was terminated by the container execution environment. The second monolithic foreground attempt reached the execution guard before completing the first matrix and also wrote no result artifact.

No outcome metric was observed, retained, or used to alter the scientific design. To make execution atomic and recoverable, the unchanged NH2 matrix is partitioned by fleet size using fixed structure and scenario identifier offsets. The concatenated result is required to contain the exact 1,152 scenarios and 34,560 replications specified by the governing protocol. NH2 robustness, NH4 primary, NH4 robustness, and finalization are separate hash-gated blocks.

This is an execution-engineering change only. Equations, parameters, seeds, graph construction, scenario identifiers, train and test splits, replication counts, statistical models, and acceptance criteria are unchanged. The revised source and runner are frozen in a replacement preregistration manifest before any block is executed.

# Stage 3 Engineering Pilot Log

## Evidence boundary

Engineering pilots are excluded from confirmatory evidence. They are used to test execution, failure handling, artifact retention, scientific implementation, and compute limits before the protocol is frozen. Pilot outcomes are not used to change hypotheses or acceptance criteria.

## Pilot 01

- Execution ID: `stage3-engineering-pilot-20260819-01`
- Status: failed and retained
- Failure: strict evidence serialization rejected a nonfinite metric
- Diagnosis: the original held-out defense assignment confounded defense case with attack class. The nominal group contained 40 non-outbreak records and no outbreak records, so ROC AUC, precision-recall AUC, and calibration parameters were not evaluable.
- Corrective action: cross both defense cases with every held-out attack class, pair them on graph, process, observation, and replication seeds, require pair completeness, and represent unsupported metrics and criteria explicitly as `not_evaluable`.
- Scientific use: excluded

## Pilot 02

- Execution ID: `stage3-engineering-pilot-20260819-02`
- Status: stopped by the declared runtime guard and retained
- Failure: wall time reached 180.362 seconds at Stage 3B scenario 191 of 240, exceeding the 180-second engineering limit
- Corrective action: increase the engineering-pilot wall limit to 300 seconds. The expanded Stage 3A held-out factorial, Stage 3B provenance checkpoints, and fixed visualization traces require more than 180 seconds on the verification workstation.
- Confirmatory impact: none to hypotheses, models, partitions, replications, estimands, statistical methods, or acceptance criteria. The confirmatory wall limit remains 1,800 seconds.
- Scientific use: excluded

## Pre-freeze rule

Any later pilot remains excluded from confirmation and uses a new execution identifier. A successful engineering pilot is required before creation of the preexecution manifest.

## Pilot 03

- Execution ID: `stage3-engineering-pilot-20260819-03`
- Status: completed
- Wall time: 190.686 seconds
- CPU time: 189.544 seconds
- Peak resident memory: 1,133.234 MB
- Execution artifacts before final evidence: 17.274 MB
- Retained rows: 4,200 Stage 3A raw, 3,600 Stage 3A held-out predictions, 480 Stage 3B raw, and 240 Stage 3B held-out predictions
- Checkpoints: 240 Stage 3B scenario Parquet files
- Visualization traces: 205 lifecycle rows and 205 DMP-state rows across five fixed traces, totaling 367,681 bytes with selection and graph metadata
- Canonical graph projection: sampled 500 of 1,000 observed-view nodes and 2,000 of 2,955 eligible retained-node edges; the source graph contained 13,433 directed layered edges
- Integrity check: all 341 execution-manifest artifact hashes verified
- Trace check: five fixed, visualization-only traces matched their raw record seeds and attack-trace digests
- Console check: replay console built offline with all four optional trace and graph availability flags true and no warnings
- Scientific use: excluded

Pilot 03 demonstrated that the full two-replication engineering matrix fits within the 300-second engineering wall limit on the verification workstation. Its observed resource use supports an engineering projection, not a direct demonstration, that the 1,800-second confirmatory limit is feasible. It did not exercise the confirmatory replication envelope, establish either research hypothesis, or change any scientific criterion.

## Pilot 04

- Execution ID: `stage3-engineering-pilot-20260819-04`
- Status: completed
- Wall time: 192.346 seconds
- CPU time: 190.322 seconds
- Peak resident memory: 1,125.594 MB
- Execution artifacts before final evidence: 17.274 MB
- Artifact integrity: all 341 execution-manifest entries verified
- Seed evidence: all four pilot domain names and the two derived bootstrap seeds are present in `stage3_evidence.json`; raw and specification tables retain per-record seeds
- Trace evidence: five selected trace seed and attack-digest tuples match their raw records
- Console load: manifest integrity verified, all five availability flags true, trace-backed scenario selected first, canonical graph identity matched, and no warning remained
- Scientific use: excluded

Pilot 04 exercised the then-current scientific runner revision. Later scientific and integrity corrections made it stale for the final pre-freeze gate. It remains preserved and excluded.

## Pilot 05

- Execution ID: `stage3-engineering-pilot-20260819-05`
- Status: completed
- Wall time: 120.711 seconds
- CPU time: 118.734 seconds
- Peak resident memory: 1,079.578 MB
- Execution artifacts before final evidence: 17.431 MB
- Retained rows: 4,200 Stage 3A raw, 3,600 Stage 3A held-out predictions, 480 Stage 3B raw, and 240 Stage 3B held-out predictions
- Scenario specifications and checkpoints: 240 specifications and 240 successful Stage 3B Parquet checkpoints
- Matrix coverage: all four declared topology x segmentation cells were present in every split and block
- Defense pairing: all 120 held-out defense-pair replication groups contained exactly both defense cases with matching graph, process, observation, base-replication, and derived-replication seeds
- Bootstrap: the common-random-number hierarchy retained Stage 3A randomization pairs and Stage 3B defense pairs with aligned replication units
- Input snapshot: all 151 nonauthoritative engineering input digests matched the working copy immediately after execution; the snapshot includes the pre-append version of this log
- Seed evidence: all four pilot domain names and all three exact derived bootstrap seeds were retained
- Evidence boundary: top-level scope is `engineering_pilot_excluded_from_confirmation`; both track dispositions are `not_adjudicated_engineering_pilot`
- Artifact integrity: all 341 execution-manifest entries matched their recorded size and SHA-256 digest
- Trace evidence: five selected trace seed and attack-digest tuples matched their raw records
- Console check: the offline replay console loaded all five optional evidence classes, all loaded integrity checks matched, and no warning was reported
- Failure artifact: absent
- Scientific use: excluded

Pilot 05 is the final post-correction engineering run. It validates execution behavior, resource limits, checkpointing, provenance, and visualization ingestion for the code used at the pre-freeze review. Its diagnostic criteria do not adjudicate either hypothesis and were not used to alter the fixed scientific acceptance thresholds.

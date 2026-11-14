# Schema notes

Each `ExperimentRecord` represents exactly one test/run. Conditions capture supported pre-ignition inputs, outcomes capture post-burn measurements, and instrument settings remain separate until a NASA source documents a physical calibration.

Every normalized measurement has its original value/unit and source provenance. Missing information is `null`; it is never inferred from a neighboring row.

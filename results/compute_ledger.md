# Compute ledger (estimated)

All jobs ran under project DD_plasma_physics. Times come from job-written timestamps where available.
ALCF's own accounting is authoritative and may differ.

| Job(s) | Purpose | Nodes | Est. node-hours |
|---|---|---:|---:|
| Polaris 7756602 | Filesystem probe (failed: no Flare mount) | 1 | ~0.02 |
| Aurora 8938194, 8938227, 8938233, 8938246, 8938252, 8938258 | Probes, argument-encoding round-trips, failed smoke1 | 1 | ~0.3 |
| Aurora 8938268/8938269 | Code staging + smoke2 (debugging, discarded) | 1 | ~0.56 |
| Aurora 8938293/8938294 | Staging + full1 (debugging, discarded) | 1 | ~0.56 |
| Aurora 8938299, 8938323 | Live track L1 (5 min) and L7 (cancelled while queued) | 1 | ~0.05 |
| Aurora 8938336/8938337 | Staging + full2 (debugging, discarded; idle wait on gpt-oss) | 1 | ~0.56 |
| Aurora 8938428/8938429 | Staging + full3 (pre-audit results) | 1 | ~0.13 |
| Aurora 8938681/8938682 | Staging + full4 (**post-audit, reported results**; 463 s of runtime) | 1 | ~0.15 |
| **Total** | | | **≈2.4–2.7 (Aurora) + ~0.02 (Polaris)** |

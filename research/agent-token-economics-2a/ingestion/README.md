# Safe Acquisition and Ingestion

No dataset is downloaded before its registry row records license,
redistribution status, estimated compressed and extracted size, and the chosen
bounded acquisition method.

Preferred order:

1. canonical metadata or dataset card;
2. manifest/index only;
3. HTTP range or streaming inspection;
4. one bounded, stratified sample;
5. shallow or sparse Git checkout only when smaller methods are unavailable.

Every acquired artifact must receive a SHA-256 entry in
`manifests/ACQUISITION_MANIFEST.jsonl`. Raw third-party trajectories are not
committed unless redistribution, privacy, and hidden-reasoning reviews all pass.

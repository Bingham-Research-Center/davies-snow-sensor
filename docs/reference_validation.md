# Reference Pi Validation Checklist

Use this checklist on the **single reference Pi** before cloning to other Pis.
Do not create the golden image until every gate passes.

## How To Run

```bash
cd /home/pi/davies-snow-sensor
SOAK_SECONDS=14400 ./scripts/reference_pi_validation.sh
```

Default soak is 4 hours (`14400` seconds). Increase to 8+ hours when possible.

## Pre-Validation Setup

- [ ] `config/station_01.yaml` has a real station ID (not `STN_XX`).
- [ ] `latitude` and `longitude` are real values (not `0.0, 0.0`).
- [ ] SSD mounted at `/mnt/snow_backup`.
- [ ] LoRa receiver/base endpoint available for success-path checks.

## Phase Results

### Phase 1: Static Checks

- [ ] `pytest -q` passes.
- [ ] Single test read command succeeds:
  `sudo venv/bin/python -m src.sensor.main --config config/station_01.yaml --test --verbose`

Notes:

```
<fill in>
```

### Phase 2: Hardware Bench Checks

- [ ] Ultrasonic test passes (`test_hardware.py -u`).
- [ ] Temperature test passes (`test_hardware.py -t`).
- [ ] OLED test passes (`test_hardware.py -o`).
- [ ] Combined test passes (`test_hardware.py --all`).

Notes:

```
<fill in>
```

### Phase 3: Soak Test

- [ ] Continuous run completed for target duration.
- [ ] No crash loops or repeated fatal errors.
- [ ] Measurement cadence remained stable.

Duration run:

```
<fill in>
```

Notes:

```
<fill in>
```

### Phase 4: Failure-Mode Checks

- [ ] LoRa-up case records `transmission_status=success`.
- [ ] LoRa-down case records `transmission_status=local_only`.
- [ ] SSD-unavailable case continues SD writes and logs warning.
- [ ] SSD-restored case resumes backup mirroring.

Notes:

```
<fill in>
```

### Phase 5: Services + Diagnostics

- [ ] `scripts/station_diagnostics.sh` reports expected station identity.
- [ ] `snow-sensor.service` is active.
- [ ] `snow-backup-monitor.timer` is active.
- [ ] Provisioning marker `/var/lib/snow-sensor/provisioned` is present.

Notes:

```
<fill in>
```

## Golden Image Gate

Create the clone image only when all below are true:

- [ ] All phases above pass.
- [ ] No unresolved warnings affecting reliability.
- [ ] Validation log saved under `data/validation/`.
- [ ] This checklist is complete and archived with the deployment notes.

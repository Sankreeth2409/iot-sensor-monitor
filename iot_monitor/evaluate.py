"""Measure the pipeline on the built-in fault scenario: detection latency, false alarms, throughput."""
from __future__ import annotations

import time

from .bus import MemoryBus
from .ingest import Ingestor
from .simulator import DEFAULT_FAULTS, default_fleet, run
from .storage import Store

STEPS, INTERVAL, START_TS = 400, 1.0, 1_700_000_000.0


def evaluate(seed=7):
    bus, store = MemoryBus(), Store()
    ing = Ingestor(bus, store)
    ing.start()
    t0 = time.perf_counter()
    sent = run(bus, default_fleet(seed), STEPS, INTERVAL, realtime=False, start_ts=START_TS,
               on_step=lambda i, ts: ing.check_stale(ts, 8 * INTERVAL))
    elapsed = time.perf_counter() - t0
    alerts = store.all_alerts()

    rows, faulted = [], set()
    for (device, metric), faults in DEFAULT_FAULTS.items():
        faulted.add((device, metric))
        for f in faults:
            t_start = START_TS + f.start * INTERVAL
            hits = [a for a in alerts if a["device"] == device and a["metric"] == metric and a["ts"] >= t_start]
            first = min(hits, key=lambda a: a["ts"]) if hits else None
            crit = [a for a in hits if a["severity"] == "critical"]
            rows.append({
                "fault": f"{f.kind} on {device}/{metric}",
                "first_alert": first["kind"] if first else "MISSED",
                "latency_steps": round((first["ts"] - t_start) / INTERVAL) if first else None,
                "critical_after_steps": round((min(a["ts"] for a in crit) - t_start) / INTERVAL) if crit else None,
            })
    false_alarms = [a for a in alerts if (a["device"], a["metric"]) not in faulted]
    first_fault = min(f.start for fl in DEFAULT_FAULTS.values() for f in fl)
    early = [a for a in alerts if (a["device"], a["metric"]) in faulted and a["ts"] < START_TS + first_fault * INTERVAL]
    return {"messages": sent, "seconds": elapsed, "msgs_per_sec": sent / elapsed, "rows": rows,
            "false_alarms": len(false_alarms) + len(early), "total_alerts": len(alerts),
            "series": len(default_fleet(seed))}


def print_report(res):
    print(f"Processed {res['messages']} messages from {res['series']} sensors in {res['seconds']:.2f} s "
          f"({res['msgs_per_sec']:.0f} msg/s, in-memory transport, SQLite storage)\n")
    print("| Injected fault | First alert | Detected after (steps) | Critical limit hit after (steps) |")
    print("|---|---|---|---|")
    for r in res["rows"]:
        crit = "-" if r["critical_after_steps"] is None else r["critical_after_steps"]
        lat = "-" if r["latency_steps"] is None else r["latency_steps"]
        print(f"| {r['fault']} | {r['first_alert']} | {lat} | {crit} |")
    print(f"\nFalse alarms on fault-free series or before the first fault: {res['false_alarms']}")
    print(f"Total alerts: {res['total_alerts']}")


def sweep(seeds=40, steps=600):
    """Robustness over many random seeds: false alarms with no faults, and missed/late detections with faults."""
    from .simulator import SensorSim  # noqa: F401  (kept for clarity)
    false_alerts = readings = 0
    for seed in range(seeds):
        bus, store = MemoryBus(), Store()
        Ingestor(bus, store).start()
        run(bus, default_fleet(seed, faults=False), steps, INTERVAL, start_ts=START_TS)
        false_alerts += len(store.all_alerts())
        readings += store.counts()["readings"]
    missed, lat = 0, {}
    for seed in range(seeds):
        bus, store = MemoryBus(), Store()
        ing = Ingestor(bus, store)
        ing.start()
        run(bus, default_fleet(seed), STEPS, INTERVAL, start_ts=START_TS,
            on_step=lambda i, ts: ing.check_stale(ts, 8 * INTERVAL))
        alerts = store.all_alerts()
        for (device, metric), faults in DEFAULT_FAULTS.items():
            f = faults[0]
            t0 = START_TS + f.start * INTERVAL
            hits = [a["ts"] for a in alerts if a["device"] == device and a["metric"] == metric and a["ts"] >= t0]
            if hits:
                lat.setdefault(f.kind, []).append(round((min(hits) - t0) / INTERVAL))
            else:
                missed += 1
    return {"seeds": seeds, "fault_free_readings": readings, "false_alerts": false_alerts,
            "faults_injected": seeds * len(DEFAULT_FAULTS), "missed": missed,
            "median_latency": {k: sorted(v)[len(v) // 2] for k, v in lat.items()}}


def print_sweep(sw):
    print(f"\nSweep over {sw['seeds']} random seeds:")
    print(f"- Fault-free: {sw['false_alerts']} false alerts in {sw['fault_free_readings']} readings "
          f"(about 1 per {sw['fault_free_readings'] // max(sw['false_alerts'], 1)} readings)")
    print(f"- With faults: {sw['faults_injected'] - sw['missed']} of {sw['faults_injected']} injected faults detected")
    print("- Median detection delay in steps: " + ", ".join(f"{k} {v}" for k, v in sw["median_latency"].items()))

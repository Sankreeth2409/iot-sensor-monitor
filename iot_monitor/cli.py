from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
import time

from .bus import MemoryBus, MqttBus
from .dashboard import make_server
from .evaluate import evaluate, print_report, print_sweep, sweep
from .ingest import Ingestor
from .schema import TOPIC_PREFIX, ValidationError, parse_reading
from .simulator import default_fleet, run
from .storage import Store


def _bus(args):
    return MqttBus(args.mqtt_host, args.mqtt_port) if args.mqtt_host else MemoryBus()


def bridge_lines(lines, bus):
    """Validate JSON lines (e.g. from the C sensor) and publish them. Returns (published, rejected)."""
    ok = bad = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            r = parse_reading(line)
        except ValidationError as exc:
            bad += 1
            print(f"skipped: {exc}", file=sys.stderr)
            continue
        bus.publish(f"{TOPIC_PREFIX}/{r.device}/{r.metric}", line)
        ok += 1
    return ok, bad


def cmd_demo(args):
    bus, store = MemoryBus(), Store(args.db)
    ing = Ingestor(bus, store)
    ing.start()
    server = make_server(store, args.host, args.port)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"Dashboard: http://{args.host}:{server.server_address[1]}  (Ctrl-C to stop)")
    stop = threading.Event()
    sim = threading.Thread(target=run, daemon=True, args=(bus, default_fleet(args.seed), args.steps),
                           kwargs=dict(interval=args.interval, realtime=True, stop=stop,
                                       on_step=lambda i, ts: ing.check_stale(ts, 8 * args.interval)))
    sim.start()
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        stop.set()
        server.shutdown()


def cmd_simulate(args):
    bus = _bus(args)
    run(bus, default_fleet(args.seed), args.steps, args.interval, realtime=True)
    bus.close()


def cmd_ingest(args):
    bus, store = _bus(args), Store(args.db)
    ing = Ingestor(bus, store)
    ing.start()
    print(f"Ingesting from {TOPIC_PREFIX}/+/+ into {args.db} (Ctrl-C to stop)")
    try:
        while True:
            time.sleep(args.stale_check)
            ing.check_stale(time.time(), args.stale_after)
    except KeyboardInterrupt:
        bus.close()


def cmd_dashboard(args):
    server = make_server(Store(args.db), args.host, args.port)
    print(f"Dashboard: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


def cmd_bridge(args):
    bus = _bus(args)
    ok, bad = bridge_lines(sys.stdin, bus)
    bus.close()
    print(json.dumps({"published": ok, "skipped": bad}), file=sys.stderr)


def cmd_evaluate(args):
    print_report(evaluate(args.seed))
    if not args.quick:
        print_sweep(sweep())


def main(argv=None):
    p = argparse.ArgumentParser(prog="iot_monitor", description=__doc__)
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, mqtt=False, db=False, web=False):
        if mqtt:
            sp.add_argument("--mqtt-host", help="MQTT broker host; omit for the in-process bus")
            sp.add_argument("--mqtt-port", type=int, default=1883)
        if db:
            sp.add_argument("--db", default=":memory:")
        if web:
            sp.add_argument("--host", default="127.0.0.1")
            sp.add_argument("--port", type=int, default=8000)

    s = sub.add_parser("demo", help="simulator + ingest + dashboard in one process, no broker needed")
    common(s, db=True, web=True)
    s.add_argument("--steps", type=int, default=400)
    s.add_argument("--interval", type=float, default=0.25)
    s.add_argument("--seed", type=int, default=7)
    s.set_defaults(fn=cmd_demo)

    s = sub.add_parser("simulate", help="publish simulated sensors (use --mqtt-host)")
    common(s, mqtt=True)
    s.add_argument("--steps", type=int, default=400)
    s.add_argument("--interval", type=float, default=1.0)
    s.add_argument("--seed", type=int, default=7)
    s.set_defaults(fn=cmd_simulate)

    s = sub.add_parser("ingest", help="subscribe, validate, store, detect")
    common(s, mqtt=True, db=True)
    s.add_argument("--stale-after", type=float, default=8.0)
    s.add_argument("--stale-check", type=float, default=2.0)
    s.set_defaults(fn=cmd_ingest)

    s = sub.add_parser("dashboard", help="serve the dashboard from a SQLite file")
    common(s, db=True, web=True)
    s.set_defaults(fn=cmd_dashboard)

    s = sub.add_parser("bridge", help="read JSON lines on stdin (e.g. from the C sensor) and publish them")
    common(s, mqtt=True)
    s.set_defaults(fn=cmd_bridge)

    s = sub.add_parser("evaluate", help="measure detection latency, false alarms, throughput")
    s.add_argument("--seed", type=int, default=7)
    s.add_argument("--quick", action="store_true", help="skip the 40-seed sweep")
    s.set_defaults(fn=cmd_evaluate)

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")
    args.fn(args)
    return 0

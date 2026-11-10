#!/usr/bin/env python3
"""UDP health-reporting agent: simulates a server and reports CPU/mem/procs/net."""
import socket, json, time, random, argparse

def clamp(v, lo, hi): return max(lo, min(hi, v))

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--id", required=True)
    p.add_argument("--server", default="10.0.0.100")
    p.add_argument("--port", type=int, default=5000)
    p.add_argument("--interval", type=float, default=1.0)
    p.add_argument("--spike-after", type=float, default=None, help="seconds after start to simulate a CPU spike")
    p.add_argument("--spike-for", type=float, default=8.0)
    p.add_argument("--duration", type=float, default=0, help="0 = run forever")
    a = p.parse_args()

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    cpu, mem = random.uniform(20, 40), random.uniform(30, 50)
    procs, net = random.randint(80, 120), random.uniform(5, 30)
    seq, start, spike_ts = 0, time.time(), None
    while True:
        now = time.time(); el = now - start
        if a.duration and el > a.duration: break
        cpu = clamp(cpu + random.uniform(-3, 3), 5, 60)      # random-walk "normal" load
        mem = clamp(mem + random.uniform(-2, 2), 20, 70)
        procs = int(clamp(procs + random.randint(-3, 3), 60, 200))
        net = clamp(net + random.uniform(-4, 4), 1, 60)
        spiking = a.spike_after is not None and a.spike_after <= el < a.spike_after + a.spike_for
        cpu_rep, event_ts = cpu, None
        if spiking:
            spike_ts = spike_ts or now
            cpu_rep, event_ts = random.uniform(92, 99), spike_ts   # ground-truth onset of the event
        else:
            spike_ts = None
        msg = {"id": a.id, "seq": seq, "ts": now, "cpu": round(cpu_rep, 1), "mem": round(mem, 1),
               "procs": procs, "net_mbps": round(net, 1), "event_ts": event_ts}
        s.sendto(json.dumps(msg).encode(), (a.server, a.port))
        seq += 1
        time.sleep(max(0, a.interval - (time.time() - now)))

if __name__ == "__main__":
    main()

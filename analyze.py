#!/usr/bin/env python3
"""python3 analyze.py  -> results/summary.csv (+ plots if matplotlib present)"""
import csv, glob, os, statistics as st

def rd(p): return list(csv.DictReader(open(p))) if os.path.exists(p) else []
def p95(x): x = sorted(x); return x[int(0.95 * (len(x) - 1))] if x else float("nan")

rows = []
for d in sorted(glob.glob("results/*_noise*")):
    mode, n, noise = os.path.basename(d).split("_")
    pk, ev, truth = rd(f"{d}/packets.csv"), rd(f"{d}/events.csv"), {r["event"]: r for r in rd(f"{d}/truth.csv")}
    delays = [float(r["delay_ms"]) for r in pk]
    per = {}
    for r in pk: per.setdefault(r["node"], []).append(int(r["seq"]))
    exp = sum(max(s) + 1 for s in per.values()); got = sum(len(s) for s in per.values())
    alert = [float(e["latency_ms"]) for e in ev if e["type"] == "ALERT_CPU" and e["node"] == "h1" and e["latency_ms"]]
    down = [float(e["ts"]) - float(truth["kill"]["ts"]) for e in ev if e["type"] == "NODE_DOWN" and e["node"] == "h2"] if "kill" in truth else []
    rows.append(dict(mode=mode, agents=n.strip(), noise=noise, reports=got, loss_pct=round(100 * (exp - got) / exp, 2) if exp else "",
                     mean_delay_ms=round(st.mean(delays), 2) if delays else "", p95_delay_ms=round(p95(delays), 2),
                     alert_latency_ms=round(alert[0], 2) if alert else "NO_ALERT",
                     down_detect_s=round(down[0], 2) if down else "NA",
                     rogue_blocked=any(e["type"] == "UNAUTHORIZED" for e in ev)))
if rows:
    w = csv.DictWriter(open("results/summary.csv", "w"), fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    for r in rows: print(r)
    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        for metric in ("p95_delay_ms", "loss_pct"):
            plt.figure()
            for m in sorted({r["mode"] for r in rows}):
                pts = sorted((int(r["agents"]), r[metric]) for r in rows if r["mode"] == m and r["noise"] == "noiseon" and r[metric] != "")
                plt.plot([p[0] for p in pts], [p[1] for p in pts], marker="o", label=m)
            plt.xlabel("number of agents"); plt.ylabel(metric); plt.legend(); plt.grid(True)
            plt.savefig(f"results/{metric}.png", dpi=120)
    except ImportError: pass

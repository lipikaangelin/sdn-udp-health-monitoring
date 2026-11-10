#!/usr/bin/env python3
"""sudo python3 experiment.py --modes baseline,qos,dynamic --sizes 5,10,20,40 --duration 50 --noise on"""
import argparse, os, subprocess, time, signal
from topo import build, SRV_IP, CTRL_IP, NOISE_SINK_IP

def run(mode, n, dur, noise, outdir):
    os.makedirs(outdir, exist_ok=True)
    subprocess.run("mn -c", shell=True, capture_output=True)
    here = os.path.dirname(os.path.abspath(__file__))
    ryu = subprocess.Popen([os.environ.get("RYU_MANAGER", "ryu-manager"), os.path.join(here, "controller.py")], env={**os.environ, "MODE": mode},
                           stdout=open(f"{outdir}/ryu.log", "w"), stderr=subprocess.STDOUT)
    time.sleep(4)
    net, h = build(n)
    truth = open(f"{outdir}/truth.csv", "w"); truth.write("event,node,ts\n")
    try:
        srv = h["srv"]
        h["root"].cmd("true")
        srv.cmd("ping -c1 -W1 %s" % CTRL_IP)
        sp = srv.popen(["python3", f"{here}/server.py", "--controller", CTRL_IP, "--outdir", outdir],
                       stdout=open(f"{outdir}/server.log", "w"), stderr=subprocess.STDOUT)
        time.sleep(1)
        t0 = time.time(); procs = {}
        for i, a in enumerate(h["agents"], 1):
            extra = ["--spike-after", "15"] if i == 1 else []
            procs[a.name] = a.popen(["python3", f"{here}/agent.py", "--id", a.name, "--server", SRV_IP] + extra,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        truth.write(f"spike,h1,{t0+15:.3f}\n")
        def at(t): time.sleep(max(0, t0 + t - time.time()))
        extras = []
        if noise == "on":
            at(5)
            extras.append(h["nk"].popen(["iperf", "-u", "-s"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            extras.append(h["ns"].popen(["iperf", "-u", "-c", NOISE_SINK_IP, "-b", "12M", "-t", str(dur - 6)],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        at(dur * 0.6)
        procs["h2"].kill(); truth.write(f"kill,h2,{time.time():.3f}\n"); truth.flush()
        at(dur * 0.75)
        extras.append(h["rogue"].popen(["python3", f"{here}/agent.py", "--id", "evil", "--server", SRV_IP, "--duration", "6"]))
        truth.write(f"rogue,evil,{time.time():.3f}\n")
        at(dur)
        for p in list(procs.values()) + extras + [sp]:
            try: p.kill()
            except Exception: pass
    finally:
        truth.close(); net.stop(); ryu.send_signal(signal.SIGINT); ryu.wait(timeout=10)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--modes", default="baseline,qos,dynamic"); ap.add_argument("--sizes", default="5,10,20,40")
    ap.add_argument("--duration", type=int, default=50); ap.add_argument("--noise", default="on")
    a = ap.parse_args()
    for mode in a.modes.split(","):
        for n in map(int, a.sizes.split(",")):
            print(f"== mode={mode} agents={n} noise={a.noise}", flush=True)
            run(mode, n, a.duration, a.noise, f"results/{mode}_{n}_noise{a.noise}")

#!/usr/bin/env python3
"""Central monitoring server (UDP). Thresholds, alerts, node-down detection,
unauthorized-sender detection, congestion detection -> notifies SDN controller."""
import socket, json, time, threading, argparse, os, re, collections

THRESH = {"cpu": 90.0, "mem": 90.0, "procs": 400, "net_mbps": 80.0}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bind", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--timeout-factor", type=float, default=3.0)
    ap.add_argument("--controller", default=None, help="controller IP for control messages")
    ap.add_argument("--ctrl-port", type=int, default=9999)
    ap.add_argument("--allowed-regex", default=r"^h\d+$")
    ap.add_argument("--congestion-ms", type=float, default=50.0)
    ap.add_argument("--outdir", default=".")
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    pk = open(os.path.join(a.outdir, "packets.csv"), "w", buffering=1); pk.write("recv_ts,node,seq,delay_ms\n")
    ev = open(os.path.join(a.outdir, "events.csv"), "w", buffering=1); ev.write("ts,type,node,detail,latency_ms\n")
    lock = threading.Lock()
    nodes, blocked = {}, set()
    window = collections.deque()           # (ts, delay_ms)
    csock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def ctrl(cmd):
        if a.controller:
            csock.sendto(json.dumps(cmd).encode(), (a.controller, a.ctrl_port))

    def log(typ, node, detail="", lat=""):
        t = time.time()
        with lock:
            ev.write(f"{t:.6f},{typ},{node},{detail},{lat}\n"); ev.flush()
        print(f"[{t:.2f}] {typ} {node} {detail} {lat}", flush=True)

    def watchdog():
        last_cong = 0
        while True:
            time.sleep(0.5); now = time.time()
            for nid, st in list(nodes.items()):
                if st["status"] == "UP" and now - st["last"] > a.timeout_factor * a.interval:
                    st["status"] = "DOWN"
                    log("NODE_DOWN", nid, "", f"{(now - st['last']) * 1000:.0f}")  # time since last heartbeat
            with lock:
                while window and window[0][0] < now - 2: window.popleft()
                d = [x[1] for x in window]
            if d and sum(d) / len(d) > a.congestion_ms and now - last_cong > 5:
                last_cong = now
                log("CONGESTION", "-", f"avg_delay_ms={sum(d)/len(d):.1f}")
                ctrl({"cmd": "congestion"})

    threading.Thread(target=watchdog, daemon=True).start()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((a.bind, a.port)); sock.settimeout(0.5)
    print(f"monitor listening on {a.bind}:{a.port}", flush=True)
    while True:
        try: data, addr = sock.recvfrom(4096)
        except socket.timeout: continue
        now = time.time()
        try:
            m = json.loads(data.decode()); nid = str(m["id"]); ts = float(m["ts"]); seq = int(m["seq"])
        except Exception:
            log("MALFORMED", addr[0]); continue
        if not re.match(a.allowed_regex, nid):
            if addr[0] not in blocked:
                blocked.add(addr[0]); log("UNAUTHORIZED", nid, addr[0]); ctrl({"cmd": "block", "ip": addr[0]})
            continue
        delay = (now - ts) * 1000
        st = nodes.setdefault(nid, {"status": "UP", "last": now, "active": {}})
        if st["status"] == "DOWN":
            st["status"] = "UP"; log("NODE_UP", nid)
        st["last"] = now
        pk.write(f"{now:.6f},{nid},{seq},{delay:.3f}\n")
        with lock: window.append((now, delay))
        for metric, limit in THRESH.items():
            v = m.get(metric)
            if v is None: continue
            if v > limit and not st["active"].get(metric):
                st["active"][metric] = True
                lat = f"{(now - m['event_ts']) * 1000:.2f}" if m.get("event_ts") else ""
                log(f"ALERT_{metric.upper()}", nid, v, lat)
            elif v <= limit:
                st["active"][metric] = False

if __name__ == "__main__":
    main()

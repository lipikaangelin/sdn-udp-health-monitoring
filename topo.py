"""Mininet topology: agents -- s1 ==(10Mbps bottleneck)== s2 -- srv, plus noise, rogue, root-ns link."""
import subprocess
from mininet.net import Mininet
from mininet.node import RemoteController, OVSKernelSwitch, Node
from mininet.log import setLogLevel

SRV_IP, CTRL_IP, NOISE_SINK_IP = "10.0.0.100", "10.0.0.254", "10.0.0.151"

def setup_qos(net, bottleneck_intfs, bottleneck_bps=10_000_000, edge_bps=100_000_000):
    """OVS linux-htb QoS on every switch port: queue0 = best effort, queue1 = high priority."""
    subprocess.run("ovs-vsctl --all destroy qos; ovs-vsctl --all destroy queue", shell=True, capture_output=True)
    for sw in net.switches:
        for intf in sw.intfList():
            if intf.name == "lo": continue
            r = bottleneck_bps if intf.name in bottleneck_intfs else edge_bps
            cmd = (f"ovs-vsctl -- set port {intf.name} qos=@q -- --id=@q create qos type=linux-htb "
                   f"other-config:max-rate={r} queues:0=@q0 queues:1=@q1 "
                   f"-- --id=@q0 create queue other-config:min-rate={r//10} other-config:max-rate={r} other-config:priority=10 "
                   f"-- --id=@q1 create queue other-config:min-rate={r//2} other-config:max-rate={r} other-config:priority=1")
            subprocess.run(cmd, shell=True, capture_output=True)

def build(n_agents, bottleneck_mbps=10):
    net = Mininet(controller=None, switch=OVSKernelSwitch, build=False, autoSetMacs=True)
    net.addController("c0", controller=RemoteController, ip="127.0.0.1", port=6653)
    s1 = net.addSwitch("s1", protocols="OpenFlow13"); s2 = net.addSwitch("s2", protocols="OpenFlow13")
    agents = [net.addHost(f"h{i}", ip=f"10.0.0.{i}/24") for i in range(1, n_agents + 1)]
    srv = net.addHost("srv", ip=f"{SRV_IP}/24")
    ns = net.addHost("ns", ip="10.0.0.150/24"); nk = net.addHost("nk", ip=f"{NOISE_SINK_IP}/24")
    rogue = net.addHost("rogue", ip="10.0.0.200/24")
    for h in agents + [ns, rogue]: net.addLink(h, s1)
    for h in [srv, nk]: net.addLink(h, s2)
    trunk = net.addLink(s1, s2)
    # root namespace attached to s2 so the controller (running in root ns) is reachable from the server host
    root = Node("root", inNamespace=False)
    rl = net.addLink(root, s2); root.setIP(CTRL_IP, 24, rl.intf1)
    net.start()
    setup_qos(net, {trunk.intf1.name, trunk.intf2.name}, bottleneck_mbps * 1_000_000)
    return net, dict(agents=agents, srv=srv, ns=ns, nk=nk, rogue=rogue, root=root)

if __name__ == "__main__":      # manual playground: sudo python3 topo.py
    from mininet.cli import CLI
    setLogLevel("info"); net, h = build(5); CLI(net); net.stop()

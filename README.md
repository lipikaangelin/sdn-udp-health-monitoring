# Remote System Health Monitoring over UDP + SDN (Mininet + Ryu)

## Install (Ubuntu VM)
    sudo apt install mininet openvswitch-switch iperf python3-pip
    pip3 install ryu matplotlib      # if Ryu fails on new Python: pip3 install eventlet==0.30.2 ryu

## Files
agent.py (UDP agent) | server.py (monitor) | controller.py (Ryu app) | topo.py (Mininet) | experiment.py | analyze.py

## Quick manual demo
    ryu-manager controller.py                      # terminal 1 (MODE=qos|dynamic|baseline env var)
    sudo python3 topo.py                           # terminal 2 -> mininet CLI
    mininet> srv python3 server.py --controller 10.0.0.254 &
    mininet> h1 python3 agent.py --id h1 --spike-after 10 &
    mininet> xterm srv      # watch alerts

## Full experiments
    sudo python3 experiment.py --modes baseline,qos,dynamic --sizes 5,10,20,40 --duration 50 --noise on
    sudo python3 experiment.py --modes baseline,qos --sizes 10 --noise off     # no-congestion reference
    python3 analyze.py

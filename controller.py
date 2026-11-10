"""Ryu OpenFlow1.3 controller. MODE env: baseline | qos | dynamic.
- learning switch
- health traffic (UDP 5000) -> priority queue 1 (qos: always; dynamic: after server reports congestion)
- UDP control channel on :9999 from monitoring server: {"cmd":"congestion"} / block / unblock"""
import os, json, socket
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ipv4, udp, ether_types
from ryu.lib import hub

HEALTH_PORT = 5000
CTRL_PORT = 9999

class HealthSDN(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.mode = os.environ.get("MODE", "baseline")
        self.prio = (self.mode == "qos")
        self.mac, self.dps, self.blocked = {}, {}, set()
        self.logger.info("MODE=%s prio=%s", self.mode, self.prio)
        hub.spawn(self._listen)

    # ---------- OpenFlow plumbing ----------
    def _miss(self, dp):
        ofp, p = dp.ofproto, dp.ofproto_parser
        self._add(dp, 0, p.OFPMatch(), [p.OFPActionOutput(ofp.OFPP_CONTROLLER, ofp.OFPCML_NO_BUFFER)])

    def _add(self, dp, prio, match, actions, idle=0):
        ofp, p = dp.ofproto, dp.ofproto_parser
        inst = [p.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)] if actions else []
        dp.send_msg(p.OFPFlowMod(datapath=dp, priority=prio, match=match, instructions=inst, idle_timeout=idle))

    def _block_flow(self, dp, ip):
        p = dp.ofproto_parser
        self._add(dp, 100, p.OFPMatch(eth_type=0x0800, ipv4_src=ip), [])   # empty actions = drop

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def _features(self, ev):
        dp = ev.msg.datapath
        self.dps[dp.id] = dp; self.mac.setdefault(dp.id, {})
        self._miss(dp)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in(self, ev):
        msg = ev.msg; dp = msg.datapath; ofp, p = dp.ofproto, dp.ofproto_parser
        in_port = msg.match["in_port"]
        pkt = packet.Packet(msg.data); eth = pkt.get_protocol(ethernet.ethernet)
        if eth.ethertype == ether_types.ETH_TYPE_LLDP: return
        self.mac[dp.id][eth.src] = in_port
        out = self.mac[dp.id].get(eth.dst, ofp.OFPP_FLOOD)
        actions = [p.OFPActionOutput(out)]
        if out != ofp.OFPP_FLOOD:
            ip, u = pkt.get_protocol(ipv4.ipv4), pkt.get_protocol(udp.udp)
            if self.prio and ip and u and u.dst_port == HEALTH_PORT:
                actions = [p.OFPActionSetQueue(1), p.OFPActionOutput(out)]
                m = p.OFPMatch(in_port=in_port, eth_dst=eth.dst, eth_type=0x0800, ip_proto=17, udp_dst=HEALTH_PORT)
                self._add(dp, 10, m, actions, idle=30)
            else:
                self._add(dp, 1, p.OFPMatch(in_port=in_port, eth_dst=eth.dst, eth_src=eth.src), actions, idle=30)
        dp.send_msg(p.OFPPacketOut(datapath=dp, buffer_id=ofp.OFP_NO_BUFFER, in_port=in_port,
                                   actions=actions, data=msg.data))

    # ---------- dynamic behaviour driven by the monitoring server ----------
    def _flush(self, dp):
        ofp, p = dp.ofproto, dp.ofproto_parser
        dp.send_msg(p.OFPFlowMod(datapath=dp, command=ofp.OFPFC_DELETE, out_port=ofp.OFPP_ANY,
                                 out_group=ofp.OFPG_ANY, match=p.OFPMatch()))
        self._miss(dp)
        for ip in self.blocked: self._block_flow(dp, ip)

    def _listen(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.bind(("0.0.0.0", CTRL_PORT))
        self.logger.info("control channel listening on UDP %d", CTRL_PORT)
        while True:
            data, addr = s.recvfrom(4096)
            try: m = json.loads(data.decode())
            except Exception: continue
            cmd = m.get("cmd"); self.logger.info("CTRL %s from %s", m, addr[0])
            if cmd == "congestion" and self.mode == "dynamic" and not self.prio:
                self.prio = True
                self.logger.info("ENABLING priority queueing for UDP %d", HEALTH_PORT)
                for dp in self.dps.values(): self._flush(dp)      # force re-learn with queue actions
            elif cmd == "block" and m.get("ip"):
                self.blocked.add(m["ip"])
                for dp in self.dps.values(): self._block_flow(dp, m["ip"])
            elif cmd == "unblock" and m.get("ip") in self.blocked:
                self.blocked.discard(m["ip"])
                for dp in self.dps.values(): self._flush(dp)

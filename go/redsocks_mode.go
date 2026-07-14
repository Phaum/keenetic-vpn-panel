package main

import (
	"fmt"
	"strings"
)

func renderRedsocksConfig(c M) string {
	t := section(c, "transparent_proxy")
	proxyType := strings.TrimSpace(fmt.Sprint(t["proxy_type"]))
	if proxyType == "" || proxyType == "auto" {
		proxyType = "socks5"
	}
	var b strings.Builder
	b.WriteString("base {\n  log_debug = off;\n  log_info = on;\n  log = stderr;\n  daemon = on;\n  redirector = iptables;\n}\n")
	b.WriteString(fmt.Sprintf("redsocks {\n  local_ip = %s;\n  local_port = %d;\n  ip = %s;\n  port = %d;\n  type = %s;\n}\n", fmt.Sprint(t["listen_ip"]), integer(c, "transparent_proxy", "listen_port"), fmt.Sprint(t["proxy_host"]), integer(c, "transparent_proxy", "proxy_port"), proxyType))
	if boolean(c, "transparent_proxy", "udp_enabled") {
		b.WriteString(fmt.Sprintf("redudp {\n  local_ip = 127.0.0.1;\n  local_port = %d;\n  ip = %s;\n  port = %d;\n  udp_timeout = 30;\n  udp_timeout_stream = 180;\n}\n", integer(c, "transparent_proxy", "udp_listen_port"), fmt.Sprint(t["proxy_host"]), integer(c, "transparent_proxy", "proxy_port")))
	}
	if boolean(c, "transparent_proxy", "dns_proxy_enabled") {
		b.WriteString(fmt.Sprintf("redudp {\n  local_ip = 127.0.0.1;\n  local_port = %d;\n  ip = %s;\n  port = %d;\n  dest_ip = %s;\n  dest_port = %d;\n  udp_timeout = 30;\n  udp_timeout_stream = 180;\n}\n", integer(c, "transparent_proxy", "dns_proxy_listen_port"), fmt.Sprint(t["proxy_host"]), integer(c, "transparent_proxy", "proxy_port"), fmt.Sprint(t["dns_upstream_ip"]), integer(c, "transparent_proxy", "dns_upstream_port")))
	}
	return b.String()
}

func renderRedsocksScripts(c M) (string, string) {
	t := section(c, "transparent_proxy")
	ipt, ip := fmt.Sprint(t["iptables_path"]), fmt.Sprint(t["ip_path"])
	chain, udpChain, dnsChain := fmt.Sprint(t["chain_name"]), fmt.Sprint(t["chain_name"])+"_UDP", fmt.Sprint(t["chain_name"])+"_DNS"
	conf, pid, bin := localPath(fmt.Sprint(t["redsocks_config_path"])), localPath(fmt.Sprint(t["redsocks_pid_file"])), fmt.Sprint(t["redsocks_bin"])
	var a, s strings.Builder
	a.WriteString("#!/opt/bin/sh\nset -eu\nIPT=" + shellQuote(ipt) + "\nIP=" + shellQuote(ip) + "\nREDSOCKS=" + shellQuote(bin) + "\nCONF=" + shellQuote(conf) + "\nPIDFILE=" + shellQuote(pid) + "\n")
	a.WriteString("command -v \"$REDSOCKS\" >/dev/null 2>&1 || { echo \"redsocks not found: $REDSOCKS\" >&2; exit 1; }\nif [ -f \"$PIDFILE\" ]; then kill \"$(cat \"$PIDFILE\")\" 2>/dev/null || true; rm -f \"$PIDFILE\"; fi\n\"$REDSOCKS\" -t -c \"$CONF\"\n\"$REDSOCKS\" -c \"$CONF\" -p \"$PIDFILE\"\n")
	a.WriteString(fmt.Sprintf("$IPT -t nat -N %s 2>/dev/null || true\n$IPT -t nat -F %s\n", shellQuote(chain), shellQuote(chain)))
	for _, bypass := range csv(t["bypass_subnets"]) {
		a.WriteString(fmt.Sprintf("$IPT -t nat -A %s -d %s -j RETURN\n", shellQuote(chain), shellQuote(bypass)))
	}
	// DNS has its own redudp instance; TCP DNS remains on the router resolver.
	a.WriteString(fmt.Sprintf("$IPT -t nat -A %s -p tcp --dport 53 -j RETURN\n$IPT -t nat -A %s -p tcp -j REDIRECT --to-ports %d\n", shellQuote(chain), shellQuote(chain), integer(c, "transparent_proxy", "listen_port")))
	for _, target := range csv(t["target_subnets"]) {
		a.WriteString(fmt.Sprintf("$IPT -t nat -C PREROUTING -s %s -p tcp -j %s 2>/dev/null || $IPT -t nat -A PREROUTING -s %s -p tcp -j %s\n", shellQuote(target), shellQuote(chain), shellQuote(target), shellQuote(chain)))
	}
	if boolean(c, "transparent_proxy", "dns_proxy_enabled") {
		a.WriteString(fmt.Sprintf("$IPT -t nat -N %s 2>/dev/null || true\n$IPT -t nat -F %s\n", shellQuote(dnsChain), shellQuote(dnsChain)))
		for _, target := range csv(t["target_subnets"]) {
			a.WriteString(fmt.Sprintf("$IPT -t nat -A %s -s %s -p udp --dport 53 -j REDIRECT --to-ports %d\n", shellQuote(dnsChain), shellQuote(target), integer(c, "transparent_proxy", "dns_proxy_listen_port")))
		}
		a.WriteString(fmt.Sprintf("$IPT -t nat -C PREROUTING -j %s 2>/dev/null || $IPT -t nat -A PREROUTING -j %s\n", shellQuote(dnsChain), shellQuote(dnsChain)))
	}
	if boolean(c, "transparent_proxy", "udp_enabled") {
		mark, table, prio := integer(c, "transparent_proxy", "udp_fwmark"), integer(c, "transparent_proxy", "udp_route_table"), integer(c, "transparent_proxy", "udp_rule_priority")
		a.WriteString(fmt.Sprintf("$IPT -t mangle -N %s 2>/dev/null || true\n$IPT -t mangle -F %s\n$IPT -t mangle -A %s -p udp --dport 53 -j RETURN\n", shellQuote(udpChain), shellQuote(udpChain), shellQuote(udpChain)))
		for _, bypass := range csv(t["bypass_subnets"]) {
			a.WriteString(fmt.Sprintf("$IPT -t mangle -A %s -d %s -j RETURN\n", shellQuote(udpChain), shellQuote(bypass)))
		}
		a.WriteString(fmt.Sprintf("$IPT -t mangle -A %s -p udp -j TPROXY --on-ip 127.0.0.1 --on-port %d --tproxy-mark %d/0xffffffff\n", shellQuote(udpChain), integer(c, "transparent_proxy", "udp_listen_port"), mark))
		for _, target := range csv(t["target_subnets"]) {
			a.WriteString(fmt.Sprintf("$IPT -t mangle -C PREROUTING -s %s -p udp -j %s 2>/dev/null || $IPT -t mangle -A PREROUTING -s %s -p udp -j %s\n", shellQuote(target), shellQuote(udpChain), shellQuote(target), shellQuote(udpChain)))
		}
		a.WriteString(fmt.Sprintf("while $IP rule del priority %d 2>/dev/null; do :; done\n$IP route replace local 0.0.0.0/0 dev lo table %d\n$IP rule add priority %d fwmark %d/0xffffffff lookup %d\n", prio, table, prio, mark, table))
	}

	s.WriteString("#!/opt/bin/sh\nset +e\nIPT=" + shellQuote(ipt) + "\nIP=" + shellQuote(ip) + "\nPIDFILE=" + shellQuote(pid) + "\n")
	for _, target := range csv(t["target_subnets"]) {
		s.WriteString(fmt.Sprintf("while $IPT -t nat -D PREROUTING -s %s -p tcp -j %s 2>/dev/null; do :; done\nwhile $IPT -t mangle -D PREROUTING -s %s -p udp -j %s 2>/dev/null; do :; done\n", shellQuote(target), shellQuote(chain), shellQuote(target), shellQuote(udpChain)))
	}
	s.WriteString(fmt.Sprintf("while $IPT -t nat -D PREROUTING -j %s 2>/dev/null; do :; done\n", shellQuote(dnsChain)))
	for _, spec := range [][2]string{{"nat", chain}, {"nat", dnsChain}, {"mangle", udpChain}} {
		s.WriteString(fmt.Sprintf("$IPT -t %s -F %s 2>/dev/null || true\n$IPT -t %s -X %s 2>/dev/null || true\n", spec[0], shellQuote(spec[1]), spec[0], shellQuote(spec[1])))
	}
	s.WriteString(fmt.Sprintf("while $IP rule del priority %d 2>/dev/null; do :; done\n$IP route flush table %d 2>/dev/null || true\n", integer(c, "transparent_proxy", "udp_rule_priority"), integer(c, "transparent_proxy", "udp_route_table")))
	s.WriteString("if [ -f \"$PIDFILE\" ]; then kill \"$(cat \"$PIDFILE\")\" 2>/dev/null || true; rm -f \"$PIDFILE\"; fi\n")
	return a.String(), s.String()
}

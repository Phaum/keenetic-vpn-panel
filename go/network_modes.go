package main

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

// renderTunPolicy generates an idempotent policy-routing setup.  Keeping all
// panel rules in dedicated chains makes repeated apply/stop operations safe.
func renderTunPolicy(c M) (string, string, string) {
	t := section(c, "transparent_proxy")
	ipt, ip, ips := fmt.Sprint(t["iptables_path"]), fmt.Sprint(t["ip_path"]), fmt.Sprint(t["ipset_path"])
	chain := fmt.Sprint(t["chain_name"])
	dnsChain := chain + "_DNS"
	netSet, domainSet := fmt.Sprint(t["destination_subnet_set"]), fmt.Sprint(t["destination_domain_set"])
	table, mark, prio := integer(c, "transparent_proxy", "tun_route_table"), integer(c, "transparent_proxy", "tun_fwmark"), integer(c, "transparent_proxy", "tun_rule_priority")
	iface := strings.TrimSpace(fmt.Sprint(t["tun_interface"]))
	var a, s, dns strings.Builder
	a.WriteString("#!/opt/bin/sh\nset -eu\n")
	s.WriteString("#!/opt/bin/sh\nset +e\n")
	a.WriteString("IP=" + shellQuote(ip) + "\nIPT=" + shellQuote(ipt) + "\nIPSET=" + shellQuote(ips) + "\n")
	if iface == "" || iface == "auto" {
		a.WriteString(`TUN_IF=""
COUNT=0
while [ "$COUNT" -lt 15 ]; do
  TUN_CANDIDATES="$($IP -o link show up 2>/dev/null | awk -F': ' '$2 ~ /^(adg|tun|tap|wg|utun)[[:alnum:]_.-]*(@.*)?$/ {sub(/@.*/, "", $2); print $2}')"
  TUN_COUNT="$(printf '%s\n' "$TUN_CANDIDATES" | awk 'NF {n++} END {print n+0}')"
  [ "$TUN_COUNT" -gt 1 ] && { echo "Multiple TUN candidates found: $TUN_CANDIDATES; configure tun_interface explicitly" >&2; exit 1; }
  [ "$TUN_COUNT" -eq 1 ] && { TUN_IF="$TUN_CANDIDATES"; break; }
  COUNT=$((COUNT+1)); sleep 1
done
[ -n "$TUN_IF" ] || { echo "TUN interface not found (expected adg*, tun*, tap*, wg* or utun*)" >&2; exit 1; }
`)
	} else {
		a.WriteString("TUN_IF=" + shellQuote(iface) + "\n")
	}
	a.WriteString("COUNT=0\nwhile ! $IP link show \"$TUN_IF\" >/dev/null 2>&1; do [ \"$COUNT\" -ge 15 ] && { echo \"TUN interface $TUN_IF does not exist\" >&2; exit 1; }; COUNT=$((COUNT+1)); sleep 1; done\n")
	a.WriteString(fmt.Sprintf("$IPSET create %s hash:net family inet -exist\n$IPSET flush %s\n", shellQuote(netSet), shellQuote(netSet)))
	for _, n := range csv(t["destination_subnets"]) {
		a.WriteString(fmt.Sprintf("$IPSET add %s %s -exist\n", shellQuote(netSet), shellQuote(n)))
	}
	a.WriteString(fmt.Sprintf("$IPSET create %s hash:ip family inet -exist\n$IPSET flush %s\n", shellQuote(domainSet), shellQuote(domainSet)))
	a.WriteString(fmt.Sprintf("$IPT -t mangle -N %s 2>/dev/null || true\n$IPT -t mangle -F %s\n", shellQuote(chain), shellQuote(chain)))
	for _, n := range csv(t["bypass_subnets"]) {
		a.WriteString(fmt.Sprintf("$IPT -t mangle -A %s -d %s -j RETURN\n", shellQuote(chain), shellQuote(n)))
	}
	selective := len(csv(t["destination_subnets"])) > 0 || len(csv(t["destination_domains"])) > 0
	for _, n := range csv(t["target_subnets"]) {
		if selective {
			for _, set := range []string{netSet, domainSet} {
				a.WriteString(fmt.Sprintf("$IPT -t mangle -A %s -s %s -p tcp -m set --match-set %s dst -j MARK --set-xmark %d/0xffffffff\n", shellQuote(chain), shellQuote(n), shellQuote(set), mark))
				a.WriteString(fmt.Sprintf("$IPT -t mangle -A %s -s %s -p udp -m set --match-set %s dst -j MARK --set-xmark %d/0xffffffff\n", shellQuote(chain), shellQuote(n), shellQuote(set), mark))
			}
		} else {
			for _, proto := range []string{"tcp", "udp"} {
				a.WriteString(fmt.Sprintf("$IPT -t mangle -A %s -s %s -p %s -j MARK --set-xmark %d/0xffffffff\n", shellQuote(chain), shellQuote(n), proto, mark))
			}
		}
	}
	a.WriteString(fmt.Sprintf("$IPT -t mangle -C PREROUTING -j %s 2>/dev/null || $IPT -t mangle -A PREROUTING -j %s\n", shellQuote(chain), shellQuote(chain)))
	a.WriteString(fmt.Sprintf("while $IP rule del priority %d 2>/dev/null; do :; done\n$IP route replace default dev \"$TUN_IF\" table %d\n$IP rule add priority %d fwmark %d/0xffffffff lookup %d\n", prio, table, prio, mark, table))
	if boolean(c, "transparent_proxy", "dns_hijack_enabled") {
		port := integer(c, "transparent_proxy", "dns_hijack_port")
		a.WriteString(fmt.Sprintf("$IPT -t nat -N %s 2>/dev/null || true\n$IPT -t nat -F %s\n", shellQuote(dnsChain), shellQuote(dnsChain)))
		for _, n := range csv(t["target_subnets"]) {
			for _, proto := range []string{"udp", "tcp"} {
				a.WriteString(fmt.Sprintf("$IPT -t nat -A %s -s %s -p %s --dport 53 -j REDIRECT --to-ports %d\n", shellQuote(dnsChain), shellQuote(n), proto, port))
			}
		}
		a.WriteString(fmt.Sprintf("$IPT -t nat -C PREROUTING -j %s 2>/dev/null || $IPT -t nat -A PREROUTING -j %s\n", shellQuote(dnsChain), shellQuote(dnsChain)))
	}

	s.WriteString("IP=" + shellQuote(ip) + "\nIPT=" + shellQuote(ipt) + "\nIPSET=" + shellQuote(ips) + "\n")
	s.WriteString(fmt.Sprintf("while $IPT -t mangle -D PREROUTING -j %s 2>/dev/null; do :; done\n$IPT -t mangle -F %s 2>/dev/null || true\n$IPT -t mangle -X %s 2>/dev/null || true\n", shellQuote(chain), shellQuote(chain), shellQuote(chain)))
	s.WriteString(fmt.Sprintf("while $IPT -t nat -D PREROUTING -j %s 2>/dev/null; do :; done\n$IPT -t nat -F %s 2>/dev/null || true\n$IPT -t nat -X %s 2>/dev/null || true\n", shellQuote(dnsChain), shellQuote(dnsChain), shellQuote(dnsChain)))
	s.WriteString(fmt.Sprintf("while $IP rule del priority %d 2>/dev/null; do :; done\n$IP route flush table %d 2>/dev/null || true\n", prio, table))
	for _, set := range []string{netSet, domainSet} {
		s.WriteString(fmt.Sprintf("$IPSET flush %s 2>/dev/null || true\n$IPSET destroy %s 2>/dev/null || true\n", shellQuote(set), shellQuote(set)))
	}
	for _, d := range csv(t["destination_domains"]) {
		dns.WriteString(fmt.Sprintf("ipset=/%s/%s\n", d, domainSet))
	}
	return a.String(), s.String(), dns.String()
}

func tunDiagnostics(c M) M {
	t := section(c, "transparent_proxy")
	warnings := []string{}
	commands := M{}
	for _, key := range []string{"ip_path", "iptables_path", "ipset_path"} {
		name := fmt.Sprint(t[key])
		path, err := exec.LookPath(name)
		commands[key] = M{"command": name, "available": err == nil, "path": path}
		if err != nil {
			warnings = append(warnings, fmt.Sprintf("Не найдена команда %s", name))
		}
	}
	interfaces := []string{}
	if out, err := exec.Command(fmt.Sprint(t["ip_path"]), "-o", "link", "show", "up").Output(); err == nil {
		for _, line := range strings.Split(string(out), "\n") {
			parts := strings.SplitN(line, ": ", 3)
			if len(parts) > 1 {
				name := strings.Split(parts[1], "@")[0]
				if strings.HasPrefix(name, "adg") || strings.HasPrefix(name, "tun") || strings.HasPrefix(name, "tap") || strings.HasPrefix(name, "wg") || strings.HasPrefix(name, "utun") {
					interfaces = append(interfaces, name)
				}
			}
		}
	}
	configured := strings.TrimSpace(fmt.Sprint(t["tun_interface"]))
	if (configured == "" || configured == "auto") && len(interfaces) == 0 {
		warnings = append(warnings, "Активный TUN-интерфейс не найден; сначала подключите AdGuard VPN")
	}
	if (configured == "" || configured == "auto") && len(interfaces) > 1 {
		warnings = append(warnings, "Найдено несколько TUN-интерфейсов; укажите нужный tun_interface явно")
	}
	if len(csv(t["destination_domains"])) > 0 && strings.TrimSpace(fmt.Sprint(t["dnsmasq_restart_command"])) == "" {
		warnings = append(warnings, "Заданы домены, но команда перезапуска dnsmasq не настроена")
	}
	forwarding := strings.TrimSpace(readSmallFile("/proc/sys/net/ipv4/ip_forward"))
	if forwarding != "1" {
		warnings = append(warnings, "IPv4 forwarding отключён")
	}
	return M{"ready": len(warnings) == 0, "commands": commands, "candidate_interfaces": interfaces, "configured_interface": configured, "ipv4_forwarding": forwarding, "warnings": warnings, "checked_at": now()}
}

func readSmallFile(path string) string {
	b, _ := os.ReadFile(filepath.Clean(path))
	return string(b)
}

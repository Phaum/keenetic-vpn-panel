package main

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
)

func shellQuote(s string) string { return "'" + strings.ReplaceAll(s, "'", "'\\''") + "'" }
func writeExecutable(path, body string) error {
	if e := os.MkdirAll(filepath.Dir(path), 0755); e != nil {
		return e
	}
	return os.WriteFile(path, []byte(body), 0755)
}
func binaryPath(c M) string {
	p := str(c, "autostart", "binary_path")
	if p == "" {
		p = filepath.Join(str(c, "autostart", "app_dir"), "keenetic-vpn-panel")
	}
	return p
}
func generateArtifacts(c M) M {
	p := localPath(str(c, "panel", "generated_script"))
	wrapper := "#!/opt/bin/sh\nset -eu\nAPP_DIR=" + shellQuote(str(c, "autostart", "app_dir")) + "\ncd \"$APP_DIR\"\nexec " + shellQuote(binaryPath(c)) + " rotate \"$@\"\n"
	e := writeExecutable(p, wrapper)
	proxy := generateProxyArtifacts(c)
	size := int64(0)
	if i, x := os.Stat(p); x == nil {
		size = i.Size()
	}
	r := M{"script_path": p, "generated_at": now(), "size": size, "transparent_proxy": proxy, "success": e == nil}
	if e != nil {
		r["error"] = e.Error()
	}
	setState("last_script_generation", r)
	return r
}
func generateProxyArtifacts(c M) M {
	t := section(c, "transparent_proxy")
	apply := localPath(fmt.Sprint(t["rules_script_path"]))
	stop := localPath(fmt.Sprint(t["stop_script_path"]))
	mode := fmt.Sprint(t["mode"])
	if mode == "tun-policy" {
		a, s, dns := renderTunPolicy(c)
		ea := writeExecutable(apply, a)
		es := writeExecutable(stop, s)
		dnsPath := localPath(fmt.Sprint(t["dnsmasq_ipset_config_path"]))
		if e := os.MkdirAll(filepath.Dir(dnsPath), 0755); e != nil && ea == nil {
			ea = e
		}
		if e := os.WriteFile(dnsPath, []byte(dns), 0644); e != nil && ea == nil {
			ea = e
		}
		return M{"success": ea == nil && es == nil, "mode": mode, "rules_script_path": apply, "stop_script_path": stop, "dnsmasq_ipset_config_path": dnsPath, "diagnostics": tunDiagnostics(c)}
	}
	if mode == "nfqueue" {
		a, s, lists, er := renderNFQueue(c)
		if er != nil {
			return M{"success": false, "mode": mode, "error": er.Error()}
		}
		ea, es := writeExecutable(apply, a), writeExecutable(stop, s)
		return M{"success": ea == nil && es == nil, "mode": mode, "rules_script_path": apply, "stop_script_path": stop, "lists": lists, "status": nfqueueStatus(c)}
	}
	if mode == "transparent-redsocks" {
		confPath := localPath(fmt.Sprint(t["redsocks_config_path"]))
		if e := os.MkdirAll(filepath.Dir(confPath), 0755); e != nil {
			return M{"success": false, "mode": mode, "error": e.Error()}
		}
		ec := os.WriteFile(confPath, []byte(renderRedsocksConfig(c)), 0600)
		a, s := renderRedsocksScripts(c)
		ea, es := writeExecutable(apply, a), writeExecutable(stop, s)
		return M{"success": ec == nil && ea == nil && es == nil, "mode": mode, "rules_script_path": apply, "stop_script_path": stop, "redsocks_config_path": confPath, "udp_enabled": t["udp_enabled"], "dns_proxy_enabled": t["dns_proxy_enabled"]}
	}
	var a, s strings.Builder
	a.WriteString("#!/opt/bin/sh\nset -eu\n")
	s.WriteString("#!/opt/bin/sh\nset +e\n")
	ea := writeExecutable(apply, a.String())
	es := writeExecutable(stop, s.String())
	return M{"success": ea == nil && es == nil, "mode": mode, "rules_script_path": apply, "stop_script_path": stop}
}
func proxyStatus(c M, vpn M) M {
	t := section(c, "transparent_proxy")
	mode, chain := fmt.Sprint(t["mode"]), fmt.Sprint(t["chain_name"])
	parent := "PREROUTING"
	if mode == "nfqueue" {
		chain, parent = fmt.Sprint(section(c, "nfqueue")["chain_name"]), "POSTROUTING"
	}
	table := "mangle"
	if mode == "transparent-redsocks" {
		table = "nat"
	}
	rulesInstalled := exec.Command(fmt.Sprint(t["iptables_path"]), "-t", table, "-C", parent, "-j", chain).Run() == nil
	available := true
	if _, err := exec.LookPath(fmt.Sprint(t["iptables_path"])); err != nil {
		available = false
	}
	running := rulesInstalled
	var extra any
	if mode == "tun-policy" {
		d := tunDiagnostics(c)
		extra = d
		for _, key := range []string{"ip_path", "iptables_path", "ipset_path"} {
			if command, ok := section(d, "commands")[key].(M); ok && command["available"] != true {
				available = false
			}
		}
	} else if mode == "nfqueue" {
		n := nfqueueStatus(c)
		extra, available, running = n, n["installed"] == true, n["running"] == true && rulesInstalled
	} else if mode == "transparent-redsocks" {
		_, redsocksErr := exec.LookPath(fmt.Sprint(t["redsocks_bin"]))
		if redsocksErr != nil {
			available = false
		}
		if boolean(c, "transparent_proxy", "udp_enabled") {
			if _, err := exec.LookPath(fmt.Sprint(t["ip_path"])); err != nil {
				available = false
			}
		}
		pid, processRunning := 0, false
		if b, err := os.ReadFile(localPath(fmt.Sprint(t["redsocks_pid_file"]))); err == nil {
			pid, _ = strconv.Atoi(strings.TrimSpace(string(b)))
			processRunning = pid > 0 && syscall.Kill(pid, 0) == nil
		}
		running = rulesInstalled && processRunning
		extra = M{"redsocks_available": redsocksErr == nil, "redsocks_running": processRunning, "redsocks_pid": pid, "udp_enabled": t["udp_enabled"], "dns_proxy_enabled": t["dns_proxy_enabled"], "udp_rules_installed": !boolean(c, "transparent_proxy", "udp_enabled") || exec.Command(fmt.Sprint(t["iptables_path"]), "-t", "mangle", "-C", "PREROUTING", "-j", chain+"_UDP").Run() == nil, "dns_rules_installed": !boolean(c, "transparent_proxy", "dns_proxy_enabled") || exec.Command(fmt.Sprint(t["iptables_path"]), "-t", "nat", "-C", "PREROUTING", "-j", chain+"_DNS").Run() == nil}
	}
	applyPath, stopPath := localPath(fmt.Sprint(t["rules_script_path"])), localPath(fmt.Sprint(t["stop_script_path"]))
	dnsPath := localPath(fmt.Sprint(t["dnsmasq_ipset_config_path"]))
	return M{"enabled": boolean(c, "transparent_proxy", "enabled"), "mode": mode, "configured": mode != "router-only", "available": available, "running": running, "rules_installed": rulesInstalled, "rule_installed": rulesInstalled, "chain_name": chain, "target_subnets": csv(t["target_subnets"]), "bypass_subnets": csv(t["bypass_subnets"]), "destination_subnets": csv(t["destination_subnets"]), "destination_domains": csv(t["destination_domains"]), "selective_enabled": len(csv(t["destination_subnets"])) > 0 || len(csv(t["destination_domains"])) > 0, "tun_interface": t["tun_interface"], "tun_route_table": t["tun_route_table"], "tun_fwmark": t["tun_fwmark"], "tun_rule_priority": t["tun_rule_priority"], "dns_hijack_enabled": t["dns_hijack_enabled"], "dns_hijack_port": t["dns_hijack_port"], "destination_subnet_set": t["destination_subnet_set"], "destination_domain_set": t["destination_domain_set"], "dnsmasq_restart_command": t["dnsmasq_restart_command"], "dnsmasq_ipset_config_path": dnsPath, "dnsmasq_ipset_config_exists": fileExists(dnsPath), "apply_script_path": applyPath, "apply_script_exists": fileExists(applyPath), "stop_script_path": stopPath, "stop_script_exists": fileExists(stopPath), "vpn_connected": vpn != nil && vpn["connected"] == true, "vpn_status": vpn, "mode_status": extra, "last_action": snapshot()["last_transparent_proxy_action"]}
}

func fileExists(path string) bool { _, err := os.Stat(path); return err == nil }
func syncProxy(c M, vpn M, reason string) M {
	mode := str(c, "transparent_proxy", "mode")
	if mode == "router-only" {
		return stopProxy(c, reason)
	}
	if mode == "nfqueue" {
		status := nfqueueStatus(c)
		if status["existing_service"] == true && !boolean(c, "nfqueue", "allow_existing_service") {
			r := M{"success": false, "reason": reason, "mode": mode, "message": "Обнаружен установленный сервис nfqws. Проверьте предупреждения и явно разрешите параллельную работу.", "nfqueue": status}
			setState("last_transparent_proxy_action", r)
			return r
		}
	}
	transport := []any{}
	if mode == "transparent-redsocks" {
		transport = append(transport, runCLI(c, "config", "set-mode", "SOCKS"))
	} else if mode == "tun-policy" {
		transport = append(transport, runCLI(c, "config", "set-mode", "TUN"), runCLI(c, "config", "set-tun-routing-mode", "NONE"))
	}
	g := generateProxyArtifacts(c)
	r := runCommand(c, []string{"sh", fmt.Sprint(g["rules_script_path"])}, 30)
	if mode == "tun-policy" && r["success"] == true && len(csv(section(c, "transparent_proxy")["destination_domains"])) > 0 {
		if command := strings.TrimSpace(str(c, "transparent_proxy", "dnsmasq_restart_command")); command != "" {
			r["dnsmasq"] = runCommand(c, []string{"sh", "-c", command}, 30)
		}
	}
	r["reason"] = reason
	r["mode"] = mode
	r["transport"] = transport
	r["artifacts"] = g
	setState("last_transparent_proxy_action", r)
	return r
}
func stopProxy(c M, reason string) M {
	g := generateProxyArtifacts(c)
	r := runCommand(c, []string{"sh", fmt.Sprint(g["stop_script_path"])}, 30)
	r["reason"] = reason
	r["mode"] = str(c, "transparent_proxy", "mode")
	setState("last_transparent_proxy_action", r)
	return r
}
func reconcileProxy(c M, vpn M, reason string) M {
	if boolean(c, "transparent_proxy", "enabled") && (str(c, "transparent_proxy", "mode") == "nfqueue" || vpn["connected"] == true) {
		return syncProxy(c, vpn, reason)
	}
	return stopProxy(c, reason)
}

func autostartStatus(c M) M {
	a := section(c, "autostart")
	pid := 0
	running := false
	if b, e := os.ReadFile(fmt.Sprint(a["pid_file"])); e == nil {
		pid, _ = strconv.Atoi(strings.TrimSpace(string(b)))
		if pid > 0 {
			running = syscall.Kill(pid, 0) == nil
		}
	}
	return M{"enabled": a["enabled"], "service_name": a["service_name"], "app_dir": a["app_dir"], "binary_path": binaryPath(c), "start_script_path": a["start_script_path"], "init_script_path": a["init_script_path"], "pid_file": a["pid_file"], "running": running, "pid": func() any {
		if pid > 0 {
			return pid
		}
		return nil
	}()}
}
func startScript(c M) string {
	return "#!/opt/bin/sh\nexport SSL_CERT_FILE=/opt/etc/ssl/certs/ca-certificates.crt\nexport HOME=/opt/home/admin\nPATH=/opt/bin:/opt/sbin:/usr/sbin:/usr/bin:/sbin:/bin\nAPP_DIR=" + shellQuote(str(c, "autostart", "app_dir")) + "\nLOG_FILE=" + shellQuote(str(c, "autostart", "log_file")) + "\ncd \"$APP_DIR\" || exit 1\nexec " + shellQuote(binaryPath(c)) + " >> \"$LOG_FILE\" 2>&1\n"
}
func initScript(c M) string {
	a := section(c, "autostart")
	return fmt.Sprintf(`#!/opt/bin/sh
NAME=%s
START_SCRIPT=%s
PID_FILE=%s
start() { [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null && return 0; mkdir -p "$(dirname "$PID_FILE")"; "$START_SCRIPT" & echo $! > "$PID_FILE"; }
stop() { [ -f "$PID_FILE" ] || return 0; PID="$(cat "$PID_FILE")"; kill "$PID" 2>/dev/null || true; COUNT=0; while kill -0 "$PID" 2>/dev/null && [ "$COUNT" -lt 10 ]; do sleep 1; COUNT=$((COUNT+1)); done; if kill -0 "$PID" 2>/dev/null; then kill -KILL "$PID" 2>/dev/null || true; sleep 1; fi; rm -f "$PID_FILE"; }
case "$1" in start) start;; stop) stop;; restart) stop; start;; status) [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null;; *) echo "Usage: $0 {start|stop|restart|status}"; exit 1;; esac
`, shellQuote(fmt.Sprint(a["service_name"])), shellQuote(fmt.Sprint(a["start_script_path"])), shellQuote(fmt.Sprint(a["pid_file"])))
}
func applyAutostart(c M, start bool) M {
	a := section(c, "autostart")
	e1 := writeExecutable(fmt.Sprint(a["start_script_path"]), startScript(c))
	e2 := writeExecutable(fmt.Sprint(a["init_script_path"]), initScript(c))
	var service any
	if (start || boolean(c, "autostart", "enabled")) && e1 == nil && e2 == nil {
		service = runCommand(c, []string{fmt.Sprint(a["init_script_path"]), "restart"}, 20)
	}
	ok := e1 == nil && e2 == nil
	r := M{"success": ok, "message": "Файлы автозапуска обновлены.", "applied_at": now(), "service_result": service, "status": autostartStatus(c)}
	setState("last_autostart_action", r)
	return r
}
func removeAutostart(c M, stop bool) M {
	a := section(c, "autostart")
	var service any
	if stop {
		service = runCommand(c, []string{fmt.Sprint(a["init_script_path"]), "stop"}, 20)
	}
	_ = os.Remove(fmt.Sprint(a["init_script_path"]))
	_ = os.Remove(fmt.Sprint(a["start_script_path"]))
	r := M{"success": true, "message": "Файлы автозапуска удалены.", "removed_at": now(), "service_result": service, "status": autostartStatus(c)}
	setState("last_autostart_action", r)
	return r
}

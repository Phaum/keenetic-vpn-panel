package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
)

type M = map[string]any

func clone(v any) any { b, _ := json.Marshal(v); var out any; _ = json.Unmarshal(b, &out); return out }
func merge(base, over M) M {
	r := clone(base).(M)
	for k, v := range over {
		if vm, ok := v.(M); ok {
			if bm, ok := r[k].(M); ok {
				r[k] = merge(bm, vm)
				continue
			}
		}
		r[k] = v
	}
	return r
}
func section(c M, name string) M {
	if v, ok := c[name].(M); ok {
		return v
	}
	v := M{}
	c[name] = v
	return v
}
func str(c M, sec, key string) string { return strings.TrimSpace(fmt.Sprint(section(c, sec)[key])) }
func integer(c M, sec, key string) int {
	v := section(c, sec)[key]
	switch n := v.(type) {
	case float64:
		return int(n)
	case int:
		return n
	case json.Number:
		i, _ := strconv.Atoi(n.String())
		return i
	}
	i, _ := strconv.Atoi(fmt.Sprint(v))
	return i
}
func boolean(c M, sec, key string) bool { v := section(c, sec)[key]; b, ok := v.(bool); return ok && b }

func defaultConfig() M {
	c := M{"panel": M{"host": "127.0.0.1", "port": 8088, "script_runner": "sh", "source_script": "sctipt_test_location.txt", "generated_script": "generated/adguardvpn-rotate.sh"}, "vpn": M{"test_url": "https://example.com/", "expected_text": "Example Domain", "top_count": 10, "timeout": 15, "connect_timeout": 8, "check_retries": 3, "check_retry_delay": 5, "switch_delay": 10}, "adguardvpn": M{"cli_command": "adguardvpn-cli", "command_timeout": 30, "locations_limit": 20}, "automation": M{"enabled": false, "check_interval": 600}, "autostart": M{"enabled": false, "service_name": "keenetic-vpn-panel", "app_dir": "/opt/share/keenetic-vpn-panel/go", "binary_path": "/opt/share/keenetic-vpn-panel/go/keenetic-vpn-panel", "log_file": "/opt/var/log/keenetic-vpn-panel.log", "pid_file": "/opt/var/run/keenetic-vpn-panel.pid", "start_script_path": "/opt/share/keenetic-vpn-panel/go/deploy/entware/start_vpn_panel.sh", "init_script_path": "/opt/etc/init.d/S99keenetic-vpn-panel"}, "logging": M{"debug_enabled": false, "debug_log_file": "/opt/var/log/adguardvpn-rotate.debug.log", "debug_max_bytes": 262144, "debug_backup_count": 2}, "paths": M{"lock_file": "/opt/tmp/adguardvpn-switch.lock", "log_file": "/opt/var/log/adguardvpn-rotate.log", "good_file": "/opt/tmp/adguardvpn-good-location.txt", "tmp_file": "/opt/tmp/adguardvpn-locations.txt", "body_file": "/opt/tmp/adguardvpn-check-body.txt"}, "resources": M{"links": []any{}}, "transparent_proxy": M{"mode": "router-only", "enabled": false, "proxy_type": "auto", "proxy_host": "127.0.0.1", "proxy_port": 1080, "listen_ip": "0.0.0.0", "listen_port": 12345, "redsocks_bin": "redsocks", "redsocks_pid_file": "generated/redsocks.pid", "redsocks_config_path": "generated/redsocks.conf", "udp_enabled": true, "udp_listen_port": 12346, "udp_route_table": 247, "udp_fwmark": 247, "udp_rule_priority": 12470, "dns_proxy_enabled": true, "dns_proxy_listen_port": 10053, "dns_upstream_ip": "1.1.1.1", "dns_upstream_port": 53, "iptables_path": "iptables", "chain_name": "KVPN_REDSOCKS", "target_subnets": "192.168.1.0/24", "bypass_subnets": "0.0.0.0/8, 10.0.0.0/8, 127.0.0.0/8, 169.254.0.0/16, 172.16.0.0/12, 192.168.0.0/16, 224.0.0.0/4, 240.0.0.0/4", "destination_subnets": "", "destination_domains": "", "ipset_path": "ipset", "destination_subnet_set": "KVPN_DST_NET", "destination_domain_set": "KVPN_DST_DNS", "dnsmasq_ipset_config_path": "generated/dnsmasq-ipset-kvpn.conf", "dnsmasq_restart_command": "", "ip_path": "ip", "tun_interface": "auto", "tun_route_table": 246, "tun_fwmark": 246, "tun_rule_priority": 12460, "dns_hijack_enabled": true, "dns_hijack_port": 53, "rules_script_path": "generated/apply-transparent-proxy.sh", "stop_script_path": "generated/remove-transparent-proxy.sh"}}
	c["nfqueue"] = M{"binary_path": "auto", "queue_num": 210, "chain_name": "KVPN_NFQWS", "tcp_ports": "80,443", "udp_ports": "443", "tcp_args": "--dpi-desync=fake,multisplit --dpi-desync-split-pos=1,midsld --dpi-desync-fooling=badseq", "udp_args": "--dpi-desync=fake --dpi-desync-repeats=6", "extra_args": "", "pid_file": "generated/nfqws.pid", "include_ips": "", "exclude_ips": "", "include_domains": "", "exclude_domains": "", "lists_dir": "generated/nfqueue", "allow_existing_service": false}
	return c
}
func loadConfig() (M, error) {
	b, e := os.ReadFile(configPath)
	if os.IsNotExist(e) {
		config := defaultConfig()
		config["setup"] = M{"completed": false, "completed_at": nil}
		if saveErr := saveConfig(config); saveErr != nil {
			return nil, saveErr
		}
		return config, nil
	}
	if e != nil {
		return nil, e
	}
	var c M
	if e = json.Unmarshal(b, &c); e != nil {
		return nil, e
	}
	merged := merge(defaultConfig(), c)
	if _, exists := merged["setup"]; !exists {
		merged["setup"] = M{"completed": false, "completed_at": nil}
	}
	return merged, nil
}
func saveConfig(c M) error {
	b, e := json.MarshalIndent(c, "", "  ")
	if e != nil {
		return e
	}
	b = append(b, '\n')
	tmp := configPath + ".tmp"
	if e = os.WriteFile(tmp, b, 0644); e != nil {
		return e
	}
	return os.Rename(tmp, configPath)
}

func migrateConfig(source string) (M, error) {
	b, err := os.ReadFile(source)
	if err != nil {
		return nil, err
	}
	var legacy M
	if err = json.Unmarshal(b, &legacy); err != nil {
		return nil, fmt.Errorf("legacy config is invalid: %w", err)
	}
	migrated := merge(defaultConfig(), legacy)
	a := section(migrated, "autostart")
	a["app_dir"] = baseDir
	a["binary_path"] = filepath.Join(baseDir, "keenetic-vpn-panel")
	a["start_script_path"] = filepath.Join(baseDir, "deploy", "entware", "start_vpn_panel.sh")
	a["init_script_path"] = "/opt/etc/init.d/S99keenetic-vpn-panel"
	setup := section(migrated, "setup")
	setup["completed"] = true
	setup["completed_at"] = now()
	migrated, err = validateConfig(migrated)
	if err != nil {
		return nil, err
	}
	if err = saveConfig(migrated); err != nil {
		return nil, err
	}
	return M{"success": true, "source": source, "destination": configPath, "config": migrated}, nil
}
func csv(v any) []string {
	fields := regexp.MustCompile(`[\r\n,]+`).Split(fmt.Sprint(v), -1)
	out := []string{}
	seen := M{}
	for _, x := range fields {
		x = strings.TrimSpace(x)
		k := strings.ToLower(x)
		if x != "" && seen[k] == nil {
			out = append(out, x)
			seen[k] = true
		}
	}
	return out
}
func normalizeNetworks(v any, field string, empty bool) (string, error) {
	xs := csv(v)
	if len(xs) == 0 && !empty {
		return "", fmt.Errorf("Field '%s' must contain at least one subnet", field)
	}
	out := []string{}
	seen := M{}
	for _, x := range xs {
		ip, n, e := net.ParseCIDR(x)
		if e != nil {
			return "", fmt.Errorf("Field '%s' contains invalid subnet '%s'", field, x)
		}
		n.IP = ip.Mask(n.Mask)
		s := n.String()
		if seen[s] == nil {
			out = append(out, s)
			seen[s] = true
		}
	}
	return strings.Join(out, ", "), nil
}

var domainRE = regexp.MustCompile(`^[a-z0-9][a-z0-9.-]*[a-z0-9]$`)

func normalizeDomains(v any, field string) (string, error) {
	out := []string{}
	seen := M{}
	for _, x := range csv(v) {
		d := strings.TrimSuffix(strings.ToLower(strings.TrimSpace(x)), ".")
		d = strings.TrimPrefix(d, "*.")
		if !domainRE.MatchString(d) || strings.Contains(d, "..") {
			return "", fmt.Errorf("Field '%s' contains invalid domain '%s'", field, x)
		}
		if seen[d] == nil {
			out = append(out, d)
			seen[d] = true
		}
	}
	return strings.Join(out, ", "), nil
}
func normalizePorts(v any, field string) (string, error) {
	raw := strings.ReplaceAll(strings.TrimSpace(fmt.Sprint(v)), " ", "")
	if raw == "" {
		return "", nil
	}
	for _, token := range strings.Split(raw, ",") {
		parts := regexp.MustCompile(`[:-]`).Split(token, -1)
		if len(parts) < 1 || len(parts) > 2 {
			return "", fmt.Errorf("Field '%s' contains invalid port range '%s'", field, token)
		}
		values := []int{}
		for _, part := range parts {
			n, err := strconv.Atoi(part)
			if err != nil || n < 1 || n > 65535 {
				return "", fmt.Errorf("Field '%s' contains invalid port '%s'", field, part)
			}
			values = append(values, n)
		}
		if len(values) == 2 && values[0] > values[1] {
			return "", fmt.Errorf("Field '%s' contains descending port range '%s'", field, token)
		}
	}
	return raw, nil
}
func validateConfig(input M) (M, error) {
	c := merge(defaultConfig(), input)
	required := [][2]string{{"panel", "host"}, {"panel", "script_runner"}, {"panel", "source_script"}, {"panel", "generated_script"}, {"vpn", "test_url"}, {"vpn", "expected_text"}, {"adguardvpn", "cli_command"}, {"paths", "lock_file"}, {"paths", "log_file"}, {"paths", "good_file"}, {"logging", "debug_log_file"}, {"autostart", "service_name"}, {"autostart", "app_dir"}, {"autostart", "log_file"}, {"autostart", "pid_file"}, {"autostart", "start_script_path"}, {"autostart", "init_script_path"}}
	for _, p := range required {
		v := str(c, p[0], p[1])
		if v == "" {
			return nil, fmt.Errorf("Field '%s.%s' must not be empty", p[0], p[1])
		}
		section(c, p[0])[p[1]] = v
	}
	ints := [][2]string{{"panel", "port"}, {"vpn", "top_count"}, {"vpn", "timeout"}, {"vpn", "connect_timeout"}, {"vpn", "check_retries"}, {"vpn", "check_retry_delay"}, {"vpn", "switch_delay"}, {"adguardvpn", "command_timeout"}, {"adguardvpn", "locations_limit"}, {"automation", "check_interval"}, {"logging", "debug_max_bytes"}, {"logging", "debug_backup_count"}, {"transparent_proxy", "proxy_port"}, {"transparent_proxy", "listen_port"}, {"transparent_proxy", "udp_listen_port"}, {"transparent_proxy", "udp_route_table"}, {"transparent_proxy", "udp_fwmark"}, {"transparent_proxy", "udp_rule_priority"}, {"transparent_proxy", "dns_proxy_listen_port"}, {"transparent_proxy", "dns_upstream_port"}, {"transparent_proxy", "tun_route_table"}, {"transparent_proxy", "tun_fwmark"}, {"transparent_proxy", "tun_rule_priority"}, {"transparent_proxy", "dns_hijack_port"}, {"nfqueue", "queue_num"}}
	for _, p := range ints {
		n := integer(c, p[0], p[1])
		if n <= 0 {
			return nil, fmt.Errorf("Field '%s.%s' must be greater than zero", p[0], p[1])
		}
		section(c, p[0])[p[1]] = n
	}
	tp := section(c, "transparent_proxy")
	mode := strings.ToLower(fmt.Sprint(tp["mode"]))
	if mode != "router-only" && mode != "transparent-redsocks" && mode != "tun-policy" && mode != "nfqueue" {
		return nil, errors.New("Field 'transparent_proxy.mode' must be one of: router-only, transparent-redsocks, tun-policy, nfqueue")
	}
	tp["mode"] = mode
	tp["enabled"] = mode != "router-only"
	for _, key := range []string{"proxy_port", "listen_port", "udp_listen_port", "dns_proxy_listen_port", "dns_upstream_port", "dns_hijack_port"} {
		if integer(c, "transparent_proxy", key) > 65535 {
			return nil, fmt.Errorf("Field 'transparent_proxy.%s' must not exceed 65535", key)
		}
	}
	if mode == "transparent-redsocks" {
		proxyType := strings.ToLower(strings.TrimSpace(fmt.Sprint(tp["proxy_type"])))
		if (boolean(c, "transparent_proxy", "udp_enabled") || boolean(c, "transparent_proxy", "dns_proxy_enabled")) && proxyType != "auto" && proxyType != "socks5" {
			return nil, errors.New("UDP/DNS through redsocks requires transparent_proxy.proxy_type to be auto or socks5")
		}
		if ip := net.ParseIP(strings.TrimSpace(fmt.Sprint(tp["dns_upstream_ip"]))); boolean(c, "transparent_proxy", "dns_proxy_enabled") && (ip == nil || ip.To4() == nil) {
			return nil, errors.New("Field 'transparent_proxy.dns_upstream_ip' must be an IPv4 address")
		}
		ports := map[int]string{}
		for _, key := range []string{"listen_port", "udp_listen_port", "dns_proxy_listen_port"} {
			if (key == "udp_listen_port" && !boolean(c, "transparent_proxy", "udp_enabled")) || (key == "dns_proxy_listen_port" && !boolean(c, "transparent_proxy", "dns_proxy_enabled")) {
				continue
			}
			port := integer(c, "transparent_proxy", key)
			if other, exists := ports[port]; exists {
				return nil, fmt.Errorf("Fields 'transparent_proxy.%s' and 'transparent_proxy.%s' must use different ports", other, key)
			}
			ports[port] = key
		}
	}
	for _, k := range []string{"target_subnets", "bypass_subnets", "destination_subnets"} {
		n, e := normalizeNetworks(tp[k], "transparent_proxy."+k, k != "target_subnets")
		if e != nil {
			return nil, e
		}
		tp[k] = n
	}
	d, e := normalizeDomains(tp["destination_domains"], "transparent_proxy.destination_domains")
	if e != nil {
		return nil, e
	}
	tp["destination_domains"] = d
	nfq := section(c, "nfqueue")
	if q := integer(c, "nfqueue", "queue_num"); q > 65535 {
		return nil, errors.New("Field 'nfqueue.queue_num' must not exceed 65535")
	}
	chainRE := regexp.MustCompile(`^[A-Za-z0-9_-]{1,24}$`)
	for sec, key := range map[string]string{"transparent_proxy": "chain_name", "nfqueue": "chain_name"} {
		if !chainRE.MatchString(strings.TrimSpace(fmt.Sprint(section(c, sec)[key]))) {
			return nil, fmt.Errorf("Field '%s.%s' must be a 1-24 character iptables chain name", sec, key)
		}
	}
	for _, k := range []string{"include_ips", "exclude_ips"} {
		n, e := normalizeNetworks(nfq[k], "nfqueue."+k, true)
		if e != nil {
			return nil, e
		}
		nfq[k] = n
	}
	for _, k := range []string{"include_domains", "exclude_domains"} {
		d, e := normalizeDomains(nfq[k], "nfqueue."+k)
		if e != nil {
			return nil, e
		}
		nfq[k] = d
	}
	for _, k := range []string{"tcp_ports", "udp_ports"} {
		v, e := normalizePorts(nfq[k], "nfqueue."+k)
		if e != nil {
			return nil, e
		}
		nfq[k] = v
	}
	if fmt.Sprint(nfq["tcp_ports"]) == "" && fmt.Sprint(nfq["udp_ports"]) == "" {
		return nil, errors.New("At least one of nfqueue.tcp_ports or nfqueue.udp_ports must be configured")
	}
	links, ok := section(c, "resources")["links"].([]any)
	if !ok {
		return nil, errors.New("Field 'resources.links' must be an array")
	}
	for i, v := range links {
		m, ok := v.(M)
		if !ok {
			return nil, fmt.Errorf("Resource #%d must be an object", i+1)
		}
		u, e := url.Parse(fmt.Sprint(m["url"]))
		if e != nil || u.Host == "" || (u.Scheme != "http" && u.Scheme != "https") {
			return nil, fmt.Errorf("Resource #%d url must be a valid http/https address", i+1)
		}
	}
	return c, nil
}
func localPath(p string) string {
	if filepath.IsAbs(p) {
		return p
	}
	return filepath.Join(baseDir, p)
}
func keys(m M) []string {
	k := make([]string, 0, len(m))
	for x := range m {
		k = append(k, x)
	}
	sort.Strings(k)
	return k
}

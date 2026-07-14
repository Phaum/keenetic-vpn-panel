package main

import (
	"bufio"
	"fmt"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"syscall"
)

var knownNFQWSLists = map[string]string{
	"/opt/etc/nfqws2/lists/user.list":          "include_domains",
	"/opt/etc/nfqws2/lists/auto.list":          "include_domains",
	"/opt/etc/nfqws2/lists/exclude.list":       "exclude_domains",
	"/opt/etc/nfqws2/lists/ipset.list":         "include_ips",
	"/opt/etc/nfqws2/lists/ipset_exclude.list": "exclude_ips",
	"/opt/etc/nfqws/user.list":                 "include_domains",
	"/opt/etc/nfqws/exclude.list":              "exclude_domains",
	"/opt/etc/nfqws/ipset.list":                "include_ips",
	"/opt/etc/nfqws/ipset_exclude.list":        "exclude_ips",
}

func discoveredNFQWSLists() map[string]string {
	result := map[string]string{}
	for path, kind := range knownNFQWSLists {
		result[path] = kind
	}
	kinds := map[string]string{"hostlist": "include_domains", "hostlist-exclude": "exclude_domains", "ipset": "include_ips", "ipset-exclude": "exclude_ips"}
	re := regexp.MustCompile(`--(hostlist|hostlist-exclude|ipset|ipset-exclude)(?:=|[ \t]+)([^ "'\\\r\n]+)`)
	for _, config := range []string{"/opt/etc/nfqws2/nfqws2.conf", "/opt/etc/nfqws/nfqws.conf", "/opt/etc/zapret/config"} {
		body, err := os.ReadFile(config)
		if err != nil {
			continue
		}
		for _, match := range re.FindAllStringSubmatch(string(body), -1) {
			path := match[2]
			if !filepath.IsAbs(path) {
				path = filepath.Join(filepath.Dir(config), path)
			}
			result[filepath.Clean(path)] = kinds[match[1]]
		}
	}
	return result
}

func normalizedListValues(raw any, domains bool) []string {
	seen := map[string]bool{}
	for _, value := range csv(raw) {
		value = strings.TrimSpace(strings.ToLower(value))
		if domains {
			value = strings.TrimPrefix(strings.TrimSuffix(value, "."), "*.")
		} else if ip := net.ParseIP(value); ip != nil {
			value = ip.String() + "/32"
		} else if _, network, err := net.ParseCIDR(value); err == nil {
			value = network.String()
		}
		if value != "" {
			seen[value] = true
		}
	}
	out := make([]string, 0, len(seen))
	for value := range seen {
		out = append(out, value)
	}
	sort.Strings(out)
	return out
}

func readNFQWSList(path string, domains bool) []string {
	f, err := os.Open(path)
	if err != nil {
		return nil
	}
	defer f.Close()
	values := []string{}
	s := bufio.NewScanner(f)
	for s.Scan() {
		line := strings.TrimSpace(strings.SplitN(s.Text(), "#", 2)[0])
		if line != "" {
			values = append(values, normalizedListValues(line, domains)...)
		}
	}
	return normalizedListValues(strings.Join(values, ","), domains)
}

func intersect(a, b []string) []string {
	set, out := map[string]bool{}, []string{}
	for _, x := range a {
		set[x] = true
	}
	for _, x := range b {
		if set[x] {
			out = append(out, x)
		}
	}
	sort.Strings(out)
	return out
}

func intersectNetworks(a, b []string) []string {
	out := []string{}
	for _, left := range a {
		lip, lnet, le := net.ParseCIDR(left)
		if le != nil {
			continue
		}
		for _, right := range b {
			rip, rnet, re := net.ParseCIDR(right)
			if re == nil && (lnet.Contains(rip) || rnet.Contains(lip)) {
				out = append(out, left)
				break
			}
		}
	}
	return normalizedListValues(strings.Join(out, ","), false)
}

func overlappingValues(kind string, a, b []string) []string {
	if strings.Contains(kind, "ips") {
		return intersectNetworks(a, b)
	}
	out := []string{}
	for _, left := range a {
		for _, right := range b {
			if left == right || strings.HasSuffix(left, "."+right) || strings.HasSuffix(right, "."+left) {
				out = append(out, left)
				break
			}
		}
	}
	return normalizedListValues(strings.Join(out, ","), true)
}

func nfqueueStatus(c M) M {
	n := section(c, "nfqueue")
	bin := fmt.Sprint(n["binary_path"])
	binPath, binErr := resolveNFQWSBinary(bin)
	existing := M{"include_domains": []string{}, "exclude_domains": []string{}, "include_ips": []string{}, "exclude_ips": []string{}}
	sources := []M{}
	for path, kind := range discoveredNFQWSLists() {
		if _, err := os.Stat(path); err != nil {
			continue
		}
		values := readNFQWSList(path, strings.Contains(kind, "domains"))
		sources = append(sources, M{"path": path, "kind": kind, "count": len(values)})
		current, _ := existing[kind].([]string)
		existing[kind] = normalizedListValues(strings.Join(append(current, values...), ","), strings.Contains(kind, "domains"))
	}
	panel := M{}
	for _, kind := range []string{"include_domains", "exclude_domains", "include_ips", "exclude_ips"} {
		panel[kind] = normalizedListValues(n[kind], strings.Contains(kind, "domains"))
	}
	warnings, overlaps := []string{}, M{}
	for _, kind := range []string{"include_domains", "exclude_domains", "include_ips", "exclude_ips"} {
		x := overlappingValues(kind, panel[kind].([]string), existing[kind].([]string))
		overlaps[kind] = x
		if len(x) > 0 {
			warnings = append(warnings, fmt.Sprintf("%s: %d записей уже есть в списках установленного nfqws", kind, len(x)))
		}
	}
	for _, pair := range [][2]string{{"include_domains", "exclude_domains"}, {"exclude_domains", "include_domains"}, {"include_ips", "exclude_ips"}, {"exclude_ips", "include_ips"}} {
		x := overlappingValues(pair[0], panel[pair[0]].([]string), existing[pair[1]].([]string))
		if len(x) > 0 {
			warnings = append(warnings, fmt.Sprintf("Конфликт %s с существующим %s: %s", pair[0], pair[1], strings.Join(x, ", ")))
		}
	}
	existingService := false
	for _, path := range []string{"/opt/etc/init.d/S51nfqws2", "/opt/etc/init.d/S51nfqws"} {
		if _, err := os.Stat(path); err == nil {
			existingService = true
		}
	}
	if existingService {
		warnings = append(warnings, "Обнаружен установленный сервис nfqws; параллельная обработка одного трафика может дать конфликт")
	}
	pid, running := 0, false
	if b, err := os.ReadFile(localPath(fmt.Sprint(n["pid_file"]))); err == nil {
		pid, _ = strconv.Atoi(strings.TrimSpace(string(b)))
		running = pid > 0 && syscall.Kill(pid, 0) == nil
	}
	return M{"installed": binErr == nil, "binary": bin, "binary_path": binPath, "running": running, "pid": pid, "queue_num": integer(c, "nfqueue", "queue_num"), "existing_service": existingService, "sources": sources, "panel_lists": panel, "existing_lists": existing, "overlaps": overlaps, "warnings": warnings, "checked_at": now()}
}

func resolveNFQWSBinary(configured string) (string, error) {
	if configured != "" && configured != "auto" {
		return exec.LookPath(configured)
	}
	for _, candidate := range []string{"nfqws2", "nfqws"} {
		if path, err := exec.LookPath(candidate); err == nil {
			return path, nil
		}
	}
	return "", fmt.Errorf("nfqws2/nfqws not found in PATH")
}

func writeNFQWSList(path string, values []string) error {
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		return err
	}
	body := ""
	if len(values) > 0 {
		body = strings.Join(values, "\n") + "\n"
	}
	return os.WriteFile(path, []byte(body), 0644)
}

func renderNFQueue(c M) (string, string, M, error) {
	n, t := section(c, "nfqueue"), section(c, "transparent_proxy")
	dir := localPath(fmt.Sprint(n["lists_dir"]))
	paths := M{}
	for _, kind := range []string{"include_domains", "exclude_domains", "include_ips", "exclude_ips"} {
		path := filepath.Join(dir, kind+".list")
		paths[kind] = path
		if err := writeNFQWSList(path, normalizedListValues(n[kind], strings.Contains(kind, "domains"))); err != nil {
			return "", "", nil, err
		}
	}
	ipt, chain := fmt.Sprint(t["iptables_path"]), fmt.Sprint(n["chain_name"])
	resolvedBinary, _ := resolveNFQWSBinary(fmt.Sprint(n["binary_path"]))
	if resolvedBinary == "" {
		resolvedBinary = fmt.Sprint(n["binary_path"])
		if resolvedBinary == "auto" {
			resolvedBinary = "nfqws2"
		}
	}
	qnum, pid := integer(c, "nfqueue", "queue_num"), localPath(fmt.Sprint(n["pid_file"]))
	var a, s strings.Builder
	a.WriteString("#!/opt/bin/sh\nset -eu\nIPT=" + shellQuote(ipt) + "\nNFQWS=" + shellQuote(resolvedBinary) + "\nPIDFILE=" + shellQuote(pid) + "\n")
	a.WriteString("command -v \"$NFQWS\" >/dev/null 2>&1 || { echo \"nfqws not found: $NFQWS\" >&2; exit 1; }\n")
	a.WriteString("if [ -f \"$PIDFILE\" ] && kill -0 \"$(cat \"$PIDFILE\")\" 2>/dev/null; then kill \"$(cat \"$PIDFILE\")\" 2>/dev/null || true; sleep 1; fi\nmkdir -p \"$(dirname \"$PIDFILE\")\"\n")
	args := []string{"--daemon", "--pidfile=" + pid, fmt.Sprintf("--qnum=%d", qnum)}
	hasDomains := len(normalizedListValues(n["include_domains"], true)) > 0
	hasIPs := len(normalizedListValues(n["include_ips"], false)) > 0
	exclusions := []string{}
	if len(normalizedListValues(n["exclude_domains"], true)) > 0 {
		exclusions = append(exclusions, "--hostlist-exclude="+fmt.Sprint(paths["exclude_domains"]))
	}
	if len(normalizedListValues(n["exclude_ips"], false)) > 0 {
		exclusions = append(exclusions, "--ipset-exclude="+fmt.Sprint(paths["exclude_ips"]))
	}
	includeProfiles := [][]string{}
	// IP and domain include lists are independent (logical OR), therefore they
	// must be separate nfqws profiles.  Exclusions are repeated in every profile.
	if hasIPs {
		includeProfiles = append(includeProfiles, append([]string{"--ipset=" + fmt.Sprint(paths["include_ips"])}, exclusions...))
	}
	if hasDomains {
		includeProfiles = append(includeProfiles, append([]string{"--hostlist=" + fmt.Sprint(paths["include_domains"])}, exclusions...))
	}
	if !hasIPs && !hasDomains {
		includeProfiles = append(includeProfiles, exclusions)
	}
	type nfqProfile struct {
		args     []string
		strategy string
	}
	profiles := []nfqProfile{}
	for _, include := range includeProfiles {
		if ports := strings.TrimSpace(fmt.Sprint(n["tcp_ports"])); ports != "" {
			profiles = append(profiles, nfqProfile{append([]string{"--filter-tcp=" + strings.ReplaceAll(ports, ":", "-")}, include...), fmt.Sprint(n["tcp_args"])})
		}
		if ports := strings.TrimSpace(fmt.Sprint(n["udp_ports"])); ports != "" {
			profiles = append(profiles, nfqProfile{append([]string{"--filter-udp=" + strings.ReplaceAll(ports, ":", "-")}, include...), fmt.Sprint(n["udp_args"])})
		}
	}
	var daemon strings.Builder
	daemon.WriteString("COMMON_ARGS=" + shellQuote(fmt.Sprint(n["extra_args"])) + "\n")
	for index, profile := range profiles {
		daemon.WriteString(fmt.Sprintf("STRATEGY_%d=%s\n", index, shellQuote(profile.strategy)))
	}
	daemon.WriteString("\"$NFQWS\"")
	for _, arg := range args {
		daemon.WriteString(" " + shellQuote(arg))
	}
	for index, profile := range profiles {
		if index > 0 {
			daemon.WriteString(" --new")
		}
		for _, arg := range profile.args {
			daemon.WriteString(" " + shellQuote(arg))
		}
		daemon.WriteString(fmt.Sprintf(" $COMMON_ARGS $STRATEGY_%d", index))
	}
	daemon.WriteString("\n")
	a.WriteString(fmt.Sprintf("$IPT -t mangle -N %s 2>/dev/null || true\n$IPT -t mangle -F %s\n", shellQuote(chain), shellQuote(chain)))
	for _, bypass := range csv(t["bypass_subnets"]) {
		a.WriteString(fmt.Sprintf("$IPT -t mangle -A %s -d %s -j RETURN\n", shellQuote(chain), shellQuote(bypass)))
	}
	for _, target := range csv(t["target_subnets"]) {
		if ports := strings.TrimSpace(fmt.Sprint(n["tcp_ports"])); ports != "" {
			a.WriteString(fmt.Sprintf("$IPT -t mangle -A %s -s %s -p tcp -m mark ! --mark 0x40000000/0x40000000 -m multiport --dports %s -j NFQUEUE --queue-num %d --queue-bypass\n", shellQuote(chain), shellQuote(target), shellQuote(ports), qnum))
		}
		if ports := strings.TrimSpace(fmt.Sprint(n["udp_ports"])); ports != "" {
			a.WriteString(fmt.Sprintf("$IPT -t mangle -A %s -s %s -p udp -m mark ! --mark 0x40000000/0x40000000 -m multiport --dports %s -j NFQUEUE --queue-num %d --queue-bypass\n", shellQuote(chain), shellQuote(target), shellQuote(ports), qnum))
		}
	}
	a.WriteString(fmt.Sprintf("$IPT -t mangle -C POSTROUTING -j %s 2>/dev/null || $IPT -t mangle -A POSTROUTING -j %s\n", shellQuote(chain), shellQuote(chain)))
	a.WriteString(daemon.String())
	s.WriteString("#!/opt/bin/sh\nset +e\nIPT=" + shellQuote(ipt) + "\nPIDFILE=" + shellQuote(pid) + "\n")
	s.WriteString(fmt.Sprintf("while $IPT -t mangle -D POSTROUTING -j %s 2>/dev/null; do :; done\n$IPT -t mangle -F %s 2>/dev/null || true\n$IPT -t mangle -X %s 2>/dev/null || true\n", shellQuote(chain), shellQuote(chain), shellQuote(chain)))
	s.WriteString("if [ -f \"$PIDFILE\" ]; then kill \"$(cat \"$PIDFILE\")\" 2>/dev/null || true; rm -f \"$PIDFILE\"; fi\n")
	return a.String(), s.String(), paths, nil
}

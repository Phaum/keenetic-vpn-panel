package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func TestNormalizeNetworks(t *testing.T) {
	got, err := normalizeNetworks("192.168.1.15/24, 10.0.0.1/8", "test", false)
	if err != nil {
		t.Fatal(err)
	}
	if got != "192.168.1.0/24, 10.0.0.0/8" {
		t.Fatalf("unexpected networks: %q", got)
	}
}

func TestNormalizeDomains(t *testing.T) {
	got, err := normalizeDomains("*.Example.COM, example.com., api.example.com", "test")
	if err != nil {
		t.Fatal(err)
	}
	if got != "example.com, api.example.com" {
		t.Fatalf("unexpected domains: %q", got)
	}
}

func TestValidateConfig(t *testing.T) {
	c := defaultConfig()
	section(c, "transparent_proxy")["target_subnets"] = "192.168.1.42/24"
	got, err := validateConfig(c)
	if err != nil {
		t.Fatal(err)
	}
	if str(got, "transparent_proxy", "target_subnets") != "192.168.1.0/24" {
		t.Fatal("subnet was not normalized")
	}
}

func TestConfigEndpoint(t *testing.T) {
	tmp := t.TempDir()
	oldBase, oldConfig := baseDir, configPath
	baseDir, configPath = tmp, filepath.Join(tmp, "config.json")
	t.Cleanup(func() { baseDir, configPath = oldBase, oldConfig })
	b, _ := json.Marshal(defaultConfig())
	if err := os.WriteFile(configPath, b, 0o644); err != nil {
		t.Fatal(err)
	}

	req := httptest.NewRequest(http.MethodGet, "/api/config", nil)
	rec := httptest.NewRecorder()
	handler(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
	var payload M
	if err := json.Unmarshal(rec.Body.Bytes(), &payload); err != nil {
		t.Fatal(err)
	}
	if section(payload, "panel")["host"] != "127.0.0.1" {
		t.Fatal("unexpected config response")
	}
}

func TestAuthenticationMarkers(t *testing.T) {
	if isAuthenticatedResult(M{"available": true, "success": true, "stdout": "Please log in first"}) {
		t.Fatal("login prompt must not be treated as authenticated")
	}
	if !isAuthenticatedResult(M{"available": true, "success": true, "stdout": "License: active"}) {
		t.Fatal("active license must be treated as authenticated")
	}
}

func TestCLIInstallationStatusMissingBinary(t *testing.T) {
	c := defaultConfig()
	section(c, "adguardvpn")["cli_command"] = "definitely-not-installed-adguardvpn-cli"
	status := cliInstallationStatus(c)
	if status["installed"] == true {
		t.Fatal("missing CLI was reported as installed")
	}
	if status["available"] == true {
		t.Fatal("missing CLI was reported as available")
	}
}

func TestCLIInstallationStatusInstalledBinary(t *testing.T) {
	tmp := t.TempDir()
	cli := filepath.Join(tmp, "adguardvpn-cli")
	if err := os.WriteFile(cli, []byte("#!/bin/sh\necho 'AdGuard VPN CLI 1.7.12'\n"), 0o755); err != nil {
		t.Fatal(err)
	}
	c := defaultConfig()
	section(c, "adguardvpn")["cli_command"] = cli
	status := cliInstallationStatus(c)
	if status["installed"] != true || status["runnable"] != true {
		t.Fatalf("installed CLI was not detected: %#v", status)
	}
	if !strings.Contains(fmt.Sprint(status["version"]), "1.7.12") {
		t.Fatalf("unexpected CLI version: %#v", status["version"])
	}
}

func TestCompleteSetup(t *testing.T) {
	tmp := t.TempDir()
	oldConfig := configPath
	configPath = filepath.Join(tmp, "config.json")
	t.Cleanup(func() { configPath = oldConfig })
	c := defaultConfig()
	c["setup"] = M{"completed": false}
	result, err := completeSetup(c, M{
		"mode": "tun-policy", "target_subnets": "192.168.1.10/24",
		"test_url": "https://example.com/", "expected_text": "Example Domain",
		"automation_enabled": true, "check_interval": float64(300),
	})
	if err != nil {
		t.Fatal(err)
	}
	if result["success"] != true {
		t.Fatal("setup did not complete")
	}
	if section(c, "transparent_proxy")["mode"] != "tun-policy" {
		t.Fatal("mode was not saved")
	}
}

func TestMigrateLegacyConfig(t *testing.T) {
	tmp := t.TempDir()
	oldBase, oldConfig := baseDir, configPath
	baseDir, configPath = filepath.Join(tmp, "go"), filepath.Join(tmp, "go", "config.json")
	if err := os.MkdirAll(baseDir, 0755); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { baseDir, configPath = oldBase, oldConfig })
	legacyPath := filepath.Join(tmp, "python-config.json")
	legacy := defaultConfig()
	section(legacy, "panel")["port"] = 8099
	a := section(legacy, "autostart")
	a["app_dir"] = "/opt/share/keenetic-vpn-panel/python"
	delete(a, "binary_path")
	b, _ := json.Marshal(legacy)
	if err := os.WriteFile(legacyPath, b, 0644); err != nil {
		t.Fatal(err)
	}
	if _, err := migrateConfig(legacyPath); err != nil {
		t.Fatal(err)
	}
	migrated, err := loadConfig()
	if err != nil {
		t.Fatal(err)
	}
	if integer(migrated, "panel", "port") != 8099 {
		t.Fatal("legacy setting was not preserved")
	}
	if str(migrated, "autostart", "app_dir") != baseDir {
		t.Fatal("old Python app path was not migrated")
	}
	if str(migrated, "autostart", "binary_path") != filepath.Join(baseDir, "keenetic-vpn-panel") {
		t.Fatal("Go binary path was not set")
	}
	if section(migrated, "setup")["completed"] != true {
		t.Fatal("migrated setup should be completed")
	}
	if section(migrated, "nfqueue")["queue_num"] == nil {
		t.Fatal("new defaults were not added")
	}
}

func TestRenderTunPolicyIsSelectiveAndIdempotent(t *testing.T) {
	c := defaultConfig()
	tp := section(c, "transparent_proxy")
	tp["mode"] = "tun-policy"
	tp["target_subnets"] = "192.168.1.0/24"
	tp["destination_subnets"] = "203.0.113.0/24"
	tp["destination_domains"] = "example.com"
	apply, stop, dns := renderTunPolicy(c)
	for _, expected := range []string{"hash:net", "--match-set", "-C PREROUTING", "route replace default", "fwmark 246/0xffffffff", "REDIRECT --to-ports 53"} {
		if !strings.Contains(apply, expected) {
			t.Errorf("TUN apply script misses %q", expected)
		}
	}
	if !strings.Contains(stop, "while $IPT -t mangle -D PREROUTING") || !strings.Contains(stop, "destroy") {
		t.Fatal("TUN stop script is not idempotent")
	}
	if !strings.Contains(dns, "ipset=/example.com/KVPN_DST_DNS") {
		t.Fatalf("unexpected dnsmasq config: %s", dns)
	}
}

func TestRenderRedsocksUDPAndDNS(t *testing.T) {
	c := defaultConfig()
	tp := section(c, "transparent_proxy")
	tp["mode"] = "transparent-redsocks"
	config := renderRedsocksConfig(c)
	apply, stop := renderRedsocksScripts(c)
	if strings.Count(config, "redudp {") != 2 {
		t.Fatalf("expected general UDP and dedicated DNS redudp sections: %s", config)
	}
	for _, expected := range []string{"dest_ip = 1.1.1.1", "dest_port = 53", "TPROXY --on-ip 127.0.0.1", "--dport 53 -j REDIRECT", "route replace local", "rule add priority"} {
		if !strings.Contains(config+apply, expected) {
			t.Errorf("redsocks artifacts miss %q", expected)
		}
	}
	for _, expected := range []string{"-t nat -D PREROUTING", "-t mangle -D PREROUTING", "rule del priority", "route flush table"} {
		if !strings.Contains(stop, expected) {
			t.Errorf("redsocks stop script misses %q", expected)
		}
	}
}

func TestValidateRedsocksUDPRequiresSOCKS5(t *testing.T) {
	c := defaultConfig()
	tp := section(c, "transparent_proxy")
	tp["mode"] = "transparent-redsocks"
	tp["proxy_type"] = "http-connect"
	if _, err := validateConfig(c); err == nil {
		t.Fatal("HTTP CONNECT must be rejected when UDP/DNS proxying is enabled")
	}
}

func TestNFQueueDetectsExistingDuplicatesAndConflicts(t *testing.T) {
	tmp := t.TempDir()
	list := filepath.Join(tmp, "user.list")
	if err := os.WriteFile(list, []byte("example.com\nblocked.example\n"), 0644); err != nil {
		t.Fatal(err)
	}
	old := knownNFQWSLists
	knownNFQWSLists = map[string]string{list: "include_domains"}
	t.Cleanup(func() { knownNFQWSLists = old })
	c := defaultConfig()
	n := section(c, "nfqueue")
	n["include_domains"] = "sub.example.com"
	n["exclude_domains"] = "sub.blocked.example"
	status := nfqueueStatus(c)
	if len(status["warnings"].([]string)) < 2 {
		t.Fatalf("expected duplicate and conflict warnings: %#v", status)
	}
}

func TestRenderNFQueueCreatesFourLists(t *testing.T) {
	tmp := t.TempDir()
	c := defaultConfig()
	n := section(c, "nfqueue")
	n["lists_dir"] = tmp
	n["pid_file"] = filepath.Join(tmp, "nfqws.pid")
	n["include_domains"] = "example.com"
	n["exclude_domains"] = "ads.example"
	n["include_ips"] = "203.0.113.1/32"
	n["exclude_ips"] = "198.51.100.0/24"
	apply, stop, lists, err := renderNFQueue(c)
	if err != nil {
		t.Fatal(err)
	}
	for _, key := range []string{"include_domains", "exclude_domains", "include_ips", "exclude_ips"} {
		if _, err := os.Stat(fmt.Sprint(lists[key])); err != nil {
			t.Errorf("missing %s list: %v", key, err)
		}
	}
	for _, expected := range []string{"--hostlist=", "--hostlist-exclude=", "--ipset=", "--ipset-exclude=", "--new", "--queue-num 210", "--queue-bypass"} {
		if !strings.Contains(apply, expected) {
			t.Errorf("NFQUEUE apply script misses %q", expected)
		}
	}
	if strings.Count(apply, "--hostlist-exclude=") != 4 || strings.Count(apply, "--ipset-exclude=") != 4 {
		t.Fatal("NFQUEUE exclusions must be applied to every include profile")
	}
	if !strings.Contains(stop, "-D POSTROUTING") {
		t.Fatal("NFQUEUE stop script does not remove jump")
	}
}

func TestGeneratedNetworkScriptsHaveValidShellSyntax(t *testing.T) {
	if _, err := exec.LookPath("sh"); err != nil {
		t.Skip("sh is not available")
	}
	c := defaultConfig()
	section(c, "transparent_proxy")["destination_domains"] = "example.com"
	tunApply, tunStop, _ := renderTunPolicy(c)
	tmp := t.TempDir()
	section(c, "nfqueue")["lists_dir"] = tmp
	nfqApply, nfqStop, _, err := renderNFQueue(c)
	if err != nil {
		t.Fatal(err)
	}
	redsocksApply, redsocksStop := renderRedsocksScripts(c)
	for name, body := range map[string]string{"tun-apply": tunApply, "tun-stop": tunStop, "nfqueue-apply": nfqApply, "nfqueue-stop": nfqStop, "redsocks-apply": redsocksApply, "redsocks-stop": redsocksStop} {
		path := filepath.Join(tmp, name+".sh")
		if err := os.WriteFile(path, []byte(body), 0755); err != nil {
			t.Fatal(err)
		}
		if output, err := exec.Command("sh", "-n", path).CombinedOutput(); err != nil {
			t.Errorf("%s syntax error: %v\n%s", name, err, output)
		}
	}
}

func TestTunPolicyInIsolatedNetworkNamespace(t *testing.T) {
	if os.Geteuid() == 0 {
		t.Skip("test is intended for rootless user namespaces")
	}
	for _, command := range []string{"unshare", "ip", "iptables"} {
		if _, err := exec.LookPath(command); err != nil {
			t.Skipf("%s is not available", command)
		}
	}
	if output, err := exec.Command("unshare", "-Urn", "true").CombinedOutput(); err != nil {
		t.Skipf("network user namespaces are unavailable: %v: %s", err, output)
	}
	c := defaultConfig()
	tp := section(c, "transparent_proxy")
	tp["ip_path"] = "/usr/bin/ip"
	tp["iptables_path"] = "/usr/sbin/iptables"
	tp["ipset_path"] = "/bin/true"
	tp["chain_name"] = "KVPN_TEST_TUN"
	tp["tun_interface"] = "adg0"
	tp["destination_subnets"] = ""
	tp["destination_domains"] = ""
	tp["dns_hijack_enabled"] = false
	apply, stop, _ := renderTunPolicy(c)
	tmp := t.TempDir()
	applyPath, stopPath := filepath.Join(tmp, "apply.sh"), filepath.Join(tmp, "stop.sh")
	if err := os.WriteFile(applyPath, []byte(apply), 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(stopPath, []byte(stop), 0755); err != nil {
		t.Fatal(err)
	}
	wrapper := fmt.Sprintf(`set -eu
ip link add adg0 type dummy
ip link set adg0 up
sh %s
sh %s
iptables -t mangle -C PREROUTING -j KVPN_TEST_TUN
iptables -t mangle -C KVPN_TEST_TUN -s 192.168.1.0/24 -p tcp -j MARK --set-xmark 246/0xffffffff
[ "$(iptables -t mangle -S PREROUTING | grep -c -- '-j KVPN_TEST_TUN')" -eq 1 ]
ip rule show | grep -q '12460:.*fwmark 0xf6.*lookup 246'
ip route show table 246 | grep -q 'default dev adg0'
sh %s
sh %s
! iptables -t mangle -S PREROUTING | grep -q KVPN_TEST_TUN
! iptables -t mangle -S KVPN_TEST_TUN >/dev/null 2>&1
! ip rule show | grep -q '^12460:'
`, shellQuote(applyPath), shellQuote(applyPath), shellQuote(stopPath), shellQuote(stopPath))
	output, err := exec.Command("unshare", "-Urn", "sh", "-c", wrapper).CombinedOutput()
	if err != nil {
		t.Fatalf("TUN integration test failed: %v\n%s", err, output)
	}
}

func TestNFQueueInIsolatedNetworkNamespace(t *testing.T) {
	for _, command := range []string{"unshare", "iptables"} {
		if _, err := exec.LookPath(command); err != nil {
			t.Skipf("%s is not available", command)
		}
	}
	if output, err := exec.Command("unshare", "-Urn", "true").CombinedOutput(); err != nil {
		t.Skipf("network user namespaces are unavailable: %v: %s", err, output)
	}
	tmp := t.TempDir()
	fake, argsLog := filepath.Join(tmp, "nfqws"), filepath.Join(tmp, "args.log")
	fakeBody := fmt.Sprintf(`#!/bin/sh
PIDFILE=""
for ARG in "$@"; do case "$ARG" in --pidfile=*) PIDFILE="${ARG#--pidfile=}";; esac; done
printf '%%s\n' "$@" > %s
sleep 30 &
echo $! > "$PIDFILE"
`, shellQuote(argsLog))
	if err := os.WriteFile(fake, []byte(fakeBody), 0755); err != nil {
		t.Fatal(err)
	}
	c := defaultConfig()
	section(c, "transparent_proxy")["iptables_path"] = "/usr/sbin/iptables"
	n := section(c, "nfqueue")
	n["binary_path"] = fake
	n["chain_name"] = "KVPN_TEST_NFQ"
	n["lists_dir"] = filepath.Join(tmp, "lists")
	n["pid_file"] = filepath.Join(tmp, "nfqws.pid")
	n["include_domains"] = "example.com"
	n["exclude_domains"] = "ads.example"
	apply, stop, _, err := renderNFQueue(c)
	if err != nil {
		t.Fatal(err)
	}
	applyPath, stopPath := filepath.Join(tmp, "apply.sh"), filepath.Join(tmp, "stop.sh")
	if err := os.WriteFile(applyPath, []byte(apply), 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(stopPath, []byte(stop), 0755); err != nil {
		t.Fatal(err)
	}
	wrapper := fmt.Sprintf(`set -eu
sh %s
sh %s
iptables -t mangle -C POSTROUTING -j KVPN_TEST_NFQ
iptables -t mangle -C KVPN_TEST_NFQ -s 192.168.1.0/24 -p tcp -m mark ! --mark 0x40000000/0x40000000 -m multiport --dports 80,443 -j NFQUEUE --queue-num 210 --queue-bypass
[ "$(iptables -t mangle -S POSTROUTING | grep -c -- '-j KVPN_TEST_NFQ')" -eq 1 ]
grep -q '^--hostlist=' %s
grep -q '^--hostlist-exclude=' %s
sh %s
sh %s
! iptables -t mangle -S POSTROUTING | grep -q KVPN_TEST_NFQ
! iptables -t mangle -S KVPN_TEST_NFQ >/dev/null 2>&1
`, shellQuote(applyPath), shellQuote(applyPath), shellQuote(argsLog), shellQuote(argsLog), shellQuote(stopPath), shellQuote(stopPath))
	output, err := exec.Command("unshare", "-Urn", "sh", "-c", wrapper).CombinedOutput()
	if err != nil {
		t.Fatalf("NFQUEUE integration test failed: %v\n%s", err, output)
	}
}

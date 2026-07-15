package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"
)

var (
	baseDir, _    = filepath.Abs(".")
	projectDir, _ = filepath.Abs("..")
	configPath    = filepath.Join(baseDir, "config.json")
	stateMu       sync.RWMutex
	actionMu      sync.Mutex
	cliMu         sync.Mutex
	state         = M{"automation_runtime": M{"thread_alive": true, "loop_running": false}}
	wake          = make(chan struct{}, 1)
	ansiRE        = regexp.MustCompile(`\x1b\[[0-9;]*m`)
)

func now() string                  { return time.Now().UTC().Format(time.RFC3339Nano) }
func setState(k string, v any)     { stateMu.Lock(); state[k] = v; stateMu.Unlock() }
func snapshot() M                  { stateMu.RLock(); defer stateMu.RUnlock(); return clone(state).(M) }
func result(ok bool, msg string) M { return M{"success": ok, "message": msg, "executed_at": now()} }
func commandEnv() []string {
	env := append(os.Environ(), "PATH=/opt/bin:/opt/sbin:/usr/sbin:/usr/bin:/sbin:/bin")
	if os.Geteuid() == 0 {
		env = append(env, "SSL_CERT_FILE=/opt/etc/ssl/certs/ca-certificates.crt", "HOME=/opt/home/admin")
	}
	return env
}

func runCommand(c M, argv []string, timeout int) M {
	r := result(false, "Команда завершилась с ошибкой.")
	r["command"] = argv
	r["stdout"] = ""
	r["stderr"] = ""
	r["returncode"] = nil
	if len(argv) == 0 {
		r["message"] = "Команда не настроена."
		r["available"] = false
		return r
	}
	if _, e := exec.LookPath(argv[0]); e != nil && !filepath.IsAbs(argv[0]) {
		r["message"] = fmt.Sprintf("Команда '%s' не найдена в PATH.", argv[0])
		r["available"] = false
		return r
	}
	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(timeout)*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, argv[0], argv[1:]...)
	cmd.Dir = baseDir
	cmd.Env = commandEnv()
	var out, er bytes.Buffer
	cmd.Stdout = &out
	cmd.Stderr = &er
	e := cmd.Run()
	r["stdout"] = out.String()
	r["stderr"] = er.String()
	r["available"] = true
	if ctx.Err() == context.DeadlineExceeded {
		r["message"] = "Команда превысила таймаут."
		return r
	}
	if e == nil {
		r["success"] = true
		r["message"] = "Команда выполнена."
		r["returncode"] = 0
	} else if x, ok := e.(*exec.ExitError); ok {
		r["returncode"] = x.ExitCode()
	}
	return r
}
func runCLI(c M, args ...string) M {
	parts := strings.Fields(str(c, "adguardvpn", "cli_command"))
	cliMu.Lock()
	defer cliMu.Unlock()
	return runCommand(c, append(parts, args...), integer(c, "adguardvpn", "command_timeout"))
}

func stripANSI(s string) string { return ansiRE.ReplaceAllString(strings.ReplaceAll(s, "\r", ""), "") }
func vpnStatus(c M) M {
	r := runCLI(c, "status")
	raw := fmt.Sprint(r["stdout"])
	clean := stripANSI(raw)
	p := M{}
	for _, line := range strings.Split(clean, "\n") {
		x := strings.SplitN(line, ":", 2)
		if len(x) == 2 {
			p[strings.ToLower(strings.TrimSpace(x[0]))] = strings.TrimSpace(x[1])
		}
	}
	location := fmt.Sprint(p["location"])
	if location == "<nil>" {
		location = ""
	}
	mode, listener := "", ""
	re := regexp.MustCompile(`(?i)^Connected to\s+(.+?)\s+in\s+(.+?)\s+mode,\s+listening on\s+(.+)$`)
	lines := strings.Split(clean, "\n")
	if len(lines) > 0 {
		if m := re.FindStringSubmatch(strings.TrimSpace(lines[0])); m != nil {
			location, mode, listener = m[1], m[2], m[3]
		}
	}
	low := strings.ToLower(clean)
	connected := (location != "" || strings.Contains(low, "connected")) && !strings.Contains(low, "not connected") && !strings.Contains(low, "disconnected")
	r["command_success"] = r["success"]
	r["success"] = r["success"].(bool) || strings.TrimSpace(clean) != ""
	r["connected"] = connected
	r["location"] = nil
	if location != "" {
		r["location"] = location
	}
	r["mode"] = nil
	if mode != "" {
		r["mode"] = mode
	}
	r["listener"] = nil
	if listener != "" {
		r["listener"] = listener
	}
	r["account"] = p["account"]
	r["device"] = p["device"]
	r["raw"] = raw
	r["clean_raw"] = clean
	r["parsed"] = p
	setState("last_vpn_status", r)
	if connected && location != "" {
		_ = os.MkdirAll(filepath.Dir(str(c, "paths", "good_file")), 0755)
		_ = os.WriteFile(str(c, "paths", "good_file"), []byte(location+"\n"), 0644)
	}
	return r
}
func vpnLocations(c M) M {
	r := runCLI(c, "list-locations")
	clean := stripANSI(fmt.Sprint(r["stdout"]))
	items := []any{}
	header := false
	for _, line := range strings.Split(clean, "\n") {
		s := strings.TrimSpace(line)
		if regexp.MustCompile(`(?i)^ISO\s+COUNTRY`).MatchString(s) {
			header = true
			continue
		}
		if strings.HasPrefix(strings.ToLower(s), "you can connect") {
			break
		}
		if !header || s == "" {
			continue
		}
		cols := regexp.MustCompile(`\s{2,}`).Split(s, -1)
		if len(cols) >= 4 {
			items = append(items, M{"code": cols[0], "country": cols[1], "city": cols[2], "score": cols[3], "raw": s})
		}
	}
	limit := integer(c, "adguardvpn", "locations_limit")
	if len(items) > limit {
		items = items[:limit]
	}
	r["items"] = items
	r["raw"] = fmt.Sprint(r["stdout"])
	r["clean_raw"] = clean
	r["command_success"] = r["success"]
	if len(items) > 0 {
		r["success"] = true
		r["message"] = fmt.Sprintf("Найдено локаций: %d", len(items))
	}
	setState("last_vpn_locations", r)
	return r
}

func httpCheck(c M) M {
	attempts := []any{}
	client := &http.Client{Timeout: time.Duration(integer(c, "vpn", "timeout")) * time.Second}
	retries := integer(c, "vpn", "check_retries")
	for i := 1; i <= retries; i++ {
		start := time.Now()
		a := M{"attempt": i, "started_at": now(), "success": false}
		req, e := http.NewRequest(http.MethodGet, str(c, "vpn", "test_url"), nil)
		if e == nil {
			req.Header.Set("User-Agent", "Mozilla/5.0")
			var resp *http.Response
			resp, e = client.Do(req)
			if e == nil {
				body, _ := io.ReadAll(resp.Body)
				resp.Body.Close()
				ok := (resp.StatusCode == 200 || resp.StatusCode == 301 || resp.StatusCode == 302) && strings.Contains(string(body), str(c, "vpn", "expected_text"))
				a["status_code"] = resp.StatusCode
				a["contains_expected_text"] = strings.Contains(string(body), str(c, "vpn", "expected_text"))
				a["duration_ms"] = float64(time.Since(start).Microseconds()) / 1000
				a["success"] = ok
				if ok {
					attempts = append(attempts, a)
					r := M{"success": true, "message": "Ресурс доступен и ожидаемый текст найден.", "attempts": attempts, "checked_at": now()}
					setState("last_check", r)
					return r
				}
			}
		}
		if e != nil {
			a["message"] = e.Error()
		}
		attempts = append(attempts, a)
		if i < retries {
			time.Sleep(time.Duration(integer(c, "vpn", "check_retry_delay")) * time.Second)
		}
	}
	r := M{"success": false, "message": "Ресурс недоступен после всех попыток.", "attempts": attempts, "checked_at": now()}
	setState("last_check", r)
	return r
}

func connectVPN(c M, location string) M {
	args := []string{"connect"}
	if location != "" {
		args = append(args, "-l", location)
	}
	r := runCLI(c, args...)
	s := vpnStatus(c)
	r["location"] = location
	r["status"] = s
	r["transparent_proxy"] = reconcileProxy(c, s, "connect")
	setState("last_cli_action", r)
	return r
}
func disconnectVPN(c M) M {
	r := runCLI(c, "disconnect")
	s := vpnStatus(c)
	r["status"] = s
	r["transparent_proxy"] = reconcileProxy(c, s, "disconnect")
	setState("last_cli_action", r)
	return r
}
func rotate(c M, trigger string) M {
	actionMu.Lock()
	defer actionMu.Unlock()
	initial := httpCheck(c)
	if initial["success"].(bool) {
		r := M{"success": true, "message": "Ресурс уже доступен, переключение не потребовалось.", "executed_at": now(), "initial_check": initial, "attempts": []any{}, "trigger": trigger, "runner": "go-native", "returncode": 0}
		setState("last_rotation", r)
		return r
	}
	locs := vpnLocations(c)
	attempts := []any{}
	for _, v := range locs["items"].([]any) {
		loc := fmt.Sprint(v.(M)["city"])
		d := disconnectVPN(c)
		time.Sleep(3 * time.Second)
		cn := connectVPN(c, loc)
		time.Sleep(time.Duration(integer(c, "vpn", "switch_delay")) * time.Second)
		check := httpCheck(c)
		a := M{"location": loc, "disconnect": d, "connect": cn, "check": check, "success": check["success"]}
		attempts = append(attempts, a)
		if check["success"].(bool) {
			r := M{"success": true, "message": "Ресурс восстановлен через " + loc + ".", "executed_at": now(), "initial_check": initial, "attempts": attempts, "locations": locs, "trigger": trigger, "runner": "go-native", "returncode": 0}
			setState("last_rotation", r)
			return r
		}
	}
	r := M{"success": false, "message": "Не удалось подобрать рабочую локацию.", "executed_at": now(), "initial_check": initial, "attempts": attempts, "locations": locs, "trigger": trigger, "runner": "go-native", "returncode": 1}
	setState("last_rotation", r)
	return r
}

func tail(path string, n int) string {
	b, e := os.ReadFile(path)
	if e != nil {
		return ""
	}
	x := strings.Split(strings.TrimSpace(string(b)), "\n")
	if len(x) > n {
		x = x[len(x)-n:]
	}
	for i, j := 0, len(x)-1; i < j; i, j = i+1, j-1 {
		x[i], x[j] = x[j], x[i]
	}
	return strings.Join(x, "\n")
}
func collectState(c M) M {
	s := snapshot()
	generated := localPath(str(c, "panel", "generated_script"))
	r := M{"config_path": configPath, "panel_url": fmt.Sprintf("http://%s:%d", str(c, "panel", "host"), integer(c, "panel", "port")), "generated_script": fileInfo(generated), "source_script": fileInfo(localPath(str(c, "panel", "source_script"))), "log_file": fileInfo(str(c, "paths", "log_file")), "debug_log_file": fileInfo(str(c, "logging", "debug_log_file")), "logging": section(c, "logging"), "automation": automationStatus(c), "transparent_proxy": proxyStatus(c, nil)}
	if links, ok := section(c, "resources")["links"].([]any); ok {
		r["resource_count"] = len(links)
	}
	for k, v := range s {
		if k != "automation_runtime" {
			r[k] = v
		}
	}
	return r
}
func fileInfo(path string) M {
	i, e := os.Stat(path)
	return M{"path": path, "exists": e == nil, "size": func() int64 {
		if e == nil {
			return i.Size()
		}
		return 0
	}()}
}

func jsonOut(w http.ResponseWriter, status int, v any) {
	b, _ := json.Marshal(v)
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_, _ = w.Write(b)
}
func readBody(r *http.Request) (M, error) {
	if r.Body == nil {
		return M{}, nil
	}
	defer r.Body.Close()
	var m M
	e := json.NewDecoder(io.LimitReader(r.Body, 1<<20)).Decode(&m)
	if e == io.EOF {
		return M{}, nil
	}
	return m, e
}
func handler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("X-Content-Type-Options", "nosniff")
	w.Header().Set("X-Frame-Options", "DENY")
	w.Header().Set("Referrer-Policy", "no-referrer")
	w.Header().Set("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
	defer func() {
		if x := recover(); x != nil {
			jsonOut(w, 500, M{"error": fmt.Sprint(x)})
		}
	}()
	c, e := loadConfig()
	if e != nil {
		jsonOut(w, 500, M{"error": e.Error()})
		return
	}
	if r.Method == http.MethodGet {
		switch r.URL.Path {
		case "/api/config":
			jsonOut(w, 200, c)
			return
		case "/api/setup/status":
			jsonOut(w, 200, setupStatus(c))
			return
		case "/api/updates/check":
			jsonOut(w, 200, checkUpdates(c))
			return
		case "/api/adguardvpn/login/status":
			jsonOut(w, 200, currentLoginStatus())
			return
		case "/api/adguardvpn/install/status":
			jsonOut(w, 200, cliInstallationStatus(c))
			return
		case "/api/state":
			jsonOut(w, 200, collectState(c))
			return
		case "/api/adguardvpn/status":
			jsonOut(w, 200, vpnStatus(c))
			return
		case "/api/adguardvpn/locations":
			jsonOut(w, 200, vpnLocations(c))
			return
		case "/api/automation/status":
			jsonOut(w, 200, automationStatus(c))
			return
		case "/api/autostart/status":
			jsonOut(w, 200, autostartStatus(c))
			return
		case "/api/transparent-proxy/status":
			jsonOut(w, 200, proxyStatus(c, vpnStatus(c)))
			return
		case "/api/transparent-proxy/diagnostics":
			jsonOut(w, 200, tunDiagnostics(c))
			return
		case "/api/nfqueue/status":
			jsonOut(w, 200, nfqueueStatus(c))
			return
		case "/api/script":
			b, _ := os.ReadFile(localPath(str(c, "panel", "generated_script")))
			jsonOut(w, 200, M{"content": string(b)})
			return
		case "/api/logs":
			kind := r.URL.Query().Get("kind")
			if kind == "debug" {
				p := str(c, "logging", "debug_log_file")
				jsonOut(w, 200, M{"content": tail(p, 200), "path": p, "kind": "debug", "debug_enabled": boolean(c, "logging", "debug_enabled")})
			} else {
				p := str(c, "paths", "log_file")
				dp := str(c, "logging", "debug_log_file")
				jsonOut(w, 200, M{"content": tail(p, 200), "path": p, "kind": "main", "debug": M{"content": tail(dp, 200), "path": dp, "enabled": boolean(c, "logging", "debug_enabled")}})
			}
			return
		}
	}
	if r.Method == http.MethodPost {
		b, e := readBody(r)
		if e != nil {
			jsonOut(w, 400, M{"error": e.Error()})
			return
		}
		switch r.URL.Path {
		case "/api/setup/complete":
			result, err := completeSetup(c, b)
			if err != nil {
				jsonOut(w, 400, M{"error": err.Error()})
				return
			}
			jsonOut(w, 200, result)
			return
		case "/api/adguardvpn/login/start":
			jsonOut(w, 200, startLogin(c))
			return
		case "/api/adguardvpn/install":
			result := installCLI(c)
			status := 200
			if result["success"] != true {
				status = 500
			}
			jsonOut(w, status, result)
			return
		case "/api/config":
			n, e := validateConfig(b)
			if e != nil {
				jsonOut(w, 400, M{"error": e.Error()})
				return
			}
			var previousCleanup any
			if str(c, "transparent_proxy", "mode") != str(n, "transparent_proxy", "mode") && str(c, "transparent_proxy", "mode") != "router-only" {
				previousCleanup = stopProxy(c, "mode-change")
			}
			if e = saveConfig(n); e != nil {
				jsonOut(w, 500, M{"error": e.Error()})
				return
			}
			g := generateArtifacts(n)
			notify()
			jsonOut(w, 200, M{"config": n, "generation": g, "previous_mode_cleanup": previousCleanup, "transparent_proxy": reconcileProxy(n, vpnStatus(n), "config-save")})
			return
		case "/api/actions/generate-script":
			jsonOut(w, 200, generateArtifacts(c))
			return
		case "/api/actions/check":
			jsonOut(w, 200, httpCheck(c))
			return
		case "/api/actions/rotate":
			jsonOut(w, 200, rotate(c, "manual"))
			return
		case "/api/actions/clear-logs":
			jsonOut(w, 200, clearLogs(c))
			return
		case "/api/automation/update":
			jsonOut(w, 200, updateAutomation(c, b))
			return
		case "/api/adguardvpn/connect":
			jsonOut(w, 200, connectVPN(c, strings.TrimSpace(fmt.Sprint(b["location"]))))
			return
		case "/api/adguardvpn/disconnect":
			jsonOut(w, 200, disconnectVPN(c))
			return
		case "/api/transparent-proxy/sync":
			jsonOut(w, 200, syncProxy(c, vpnStatus(c), "api"))
			return
		case "/api/transparent-proxy/stop":
			jsonOut(w, 200, stopProxy(c, "api"))
			return
		case "/api/autostart/apply":
			jsonOut(w, 200, applyAutostart(c, b["start_now"] == true))
			return
		case "/api/autostart/remove":
			jsonOut(w, 200, removeAutostart(c, b["stop_now"] != false))
			return
		case "/api/actions/update-project":
			jsonOut(w, 200, runCommand(c, []string{filepath.Join(baseDir, "install", "update.sh")}, 900))
			return
		case "/api/actions/restart-panel":
			jsonOut(w, 200, scheduleRestart(c))
			return
		}
	}
	if r.Method == http.MethodGet {
		path := r.URL.Path
		if path == "/" {
			path = "/index.html"
		}
		if path == "/styles.css" {
			w.Header().Set("Cache-Control", "no-store")
			http.ServeFile(w, r, filepath.Join(baseDir, "web", "styles.css"))
			return
		}
		if path == "/app.js" {
			w.Header().Set("Content-Type", "application/javascript; charset=utf-8")
			w.Header().Set("Cache-Control", "no-store")
			for _, asset := range []string{
				filepath.Join(projectDir, "web", "app.js"),
				filepath.Join(baseDir, "web", "ui.js"),
			} {
				content, err := os.ReadFile(asset)
				if err != nil {
					http.Error(w, err.Error(), http.StatusInternalServerError)
					return
				}
				_, _ = w.Write(content)
				_, _ = w.Write([]byte("\n"))
			}
			return
		}
		root := filepath.Join(projectDir, "web")
		if path == "/assets/logo.ico" {
			root = projectDir
		}
		clean := filepath.Clean(strings.TrimPrefix(path, "/"))
		if strings.Contains(clean, "..") {
			http.NotFound(w, r)
			return
		}
		http.ServeFile(w, r, filepath.Join(root, clean))
		return
	}
	http.NotFound(w, r)
}

func notify() {
	select {
	case wake <- struct{}{}:
	default:
	}
}
func automationStatus(c M) M {
	s := snapshot()
	rt := section(s, "automation_runtime")
	return M{"enabled": boolean(c, "automation", "enabled"), "check_interval": integer(c, "automation", "check_interval"), "thread_alive": true, "loop_running": rt["loop_running"], "last_started_at": rt["last_started_at"], "last_completed_at": rt["last_completed_at"], "next_check_at": rt["next_check_at"], "last_error": rt["last_error"], "last_result": rt["last_result"], "last_action": s["last_automation_action"]}
}
func automation() {
	for {
		c, e := loadConfig()
		if e != nil {
			time.Sleep(time.Minute)
			continue
		}
		d := time.Duration(integer(c, "automation", "check_interval")) * time.Second
		if !boolean(c, "automation", "enabled") {
			d = time.Hour
		} else {
			stateMu.Lock()
			rt := section(state, "automation_runtime")
			rt["loop_running"] = true
			rt["last_started_at"] = now()
			stateMu.Unlock()
			r := rotate(c, "automation")
			setState("last_automation_action", r)
			stateMu.Lock()
			rt = section(state, "automation_runtime")
			rt["loop_running"] = false
			rt["last_completed_at"] = now()
			rt["last_result"] = r
			rt["next_check_at"] = time.Now().Add(d).UTC().Format(time.RFC3339Nano)
			stateMu.Unlock()
		}
		select {
		case <-time.After(d):
		case <-wake:
		}
	}
}
func updateAutomation(c, b M) M {
	a := section(c, "automation")
	if v, ok := b["enabled"].(bool); ok {
		a["enabled"] = v
	}
	if v := b["check_interval"]; v != nil {
		n, _ := strconv.Atoi(fmt.Sprint(v))
		if f, ok := v.(float64); ok {
			n = int(f)
		}
		if n <= 0 {
			return M{"success": false, "message": "Интервал должен быть больше нуля."}
		}
		a["check_interval"] = n
	}
	_ = saveConfig(c)
	notify()
	return M{"success": true, "message": "Настройки автоматизации обновлены.", "config": a, "status": automationStatus(c), "updated_at": now()}
}
func clearLogs(c M) M {
	cleared := []string{}
	for _, p := range []string{str(c, "paths", "log_file"), str(c, "logging", "debug_log_file")} {
		_ = os.MkdirAll(filepath.Dir(p), 0755)
		if os.WriteFile(p, nil, 0644) == nil {
			cleared = append(cleared, p)
		}
		matches, _ := filepath.Glob(p + ".*")
		for _, x := range matches {
			_ = os.Remove(x)
		}
	}
	setState("last_check", nil)
	return M{"success": true, "message": "Логи очищены.", "executed_at": now(), "cleared": cleared}
}
func scheduleRestart(c M) M {
	delay := 2
	initPath := str(c, "autostart", "init_script_path")
	method := "self-reexec"
	var cmd *exec.Cmd
	if info, err := os.Stat(initPath); err == nil && !info.IsDir() && info.Mode().Perm()&0111 != 0 {
		method = "entware-init"
		cmd = exec.Command("sh", "-c", `sleep "$1"; exec "$2" restart`, "restart-helper", strconv.Itoa(delay), initPath)
	} else {
		executable, err := os.Executable()
		if err != nil {
			return M{"success": false, "message": "Не удалось определить исполняемый файл панели: " + err.Error(), "executed_at": now()}
		}
		// A detached helper waits until the HTTP response has been sent, stops the
		// current process, waits for the listening socket to close and execs a new
		// copy in the same working directory. This also makes local development
		// restartable when no Entware init script exists.
		cmd = exec.Command("sh", "-c", `sleep "$1"; kill -TERM "$2" 2>/dev/null || true; COUNT=0; while kill -0 "$2" 2>/dev/null && [ "$COUNT" -lt 50 ]; do sleep 0.1; COUNT=$((COUNT+1)); done; cd "$3" || exit 1; exec "$4"`, "restart-helper", strconv.Itoa(delay), strconv.Itoa(os.Getpid()), baseDir, executable)
	}
	cmd.Dir = baseDir
	cmd.Env = commandEnv()
	cmd.SysProcAttr = &syscall.SysProcAttr{Setsid: true}
	if err := cmd.Start(); err != nil {
		return M{"success": false, "message": "Не удалось запустить helper перезапуска: " + err.Error(), "executed_at": now(), "restart_method": method}
	}
	_ = cmd.Process.Release()
	return M{"success": true, "message": "Перезапуск панели запланирован через 2 сек.", "executed_at": now(), "restart_scheduled": true, "restart_method": method, "restart_delay_seconds": delay}
}

func main() {
	if exe, e := os.Executable(); e == nil {
		candidate := filepath.Dir(exe)
		if _, e = os.Stat(filepath.Join(candidate, "go.mod")); e == nil {
			baseDir = candidate
			projectDir = filepath.Dir(candidate)
			configPath = filepath.Join(baseDir, "config.json")
		}
	}
	if len(os.Args) == 3 && os.Args[1] == "migrate-config" {
		r, err := migrateConfig(os.Args[2])
		if err != nil {
			_ = json.NewEncoder(os.Stdout).Encode(M{"success": false, "error": err.Error()})
			os.Exit(1)
		}
		_ = json.NewEncoder(os.Stdout).Encode(r)
		return
	}
	c, e := loadConfig()
	if e != nil {
		fmt.Fprintln(os.Stderr, e)
		os.Exit(1)
	}
	if len(os.Args) > 1 {
		var r M
		switch os.Args[1] {
		case "rotate":
			r = rotate(c, "cli")
		case "sync-transparent-proxy":
			r = syncProxy(c, vpnStatus(c), "cli")
		case "stop-transparent-proxy":
			r = stopProxy(c, "cli")
		case "migrate-config":
			fmt.Fprintln(os.Stderr, "usage: keenetic-vpn-panel migrate-config SOURCE_CONFIG")
			os.Exit(2)
		default:
			fmt.Fprintln(os.Stderr, "unknown command")
			os.Exit(2)
		}
		_ = json.NewEncoder(os.Stdout).Encode(r)
		if r["success"] != true {
			os.Exit(1)
		}
		return
	}
	generateArtifacts(c)
	go automation()
	addr := fmt.Sprintf("%s:%d", str(c, "panel", "host"), integer(c, "panel", "port"))
	fmt.Printf("VPN panel running on http://%s\n", addr)
	s := &http.Server{
		Addr:              addr,
		Handler:           http.HandlerFunc(handler),
		ReadHeaderTimeout: 10 * time.Second,
		ReadTimeout:       15 * time.Second,
		WriteTimeout:      60 * time.Second,
		IdleTimeout:       60 * time.Second,
		MaxHeaderBytes:    1 << 20,
	}
	if e = s.ListenAndServe(); e != nil && e != http.ErrServerClosed {
		fmt.Fprintln(os.Stderr, e)
		os.Exit(1)
	}
}

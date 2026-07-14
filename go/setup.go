package main

import (
	"bytes"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"time"
)

type synchronizedBuffer struct {
	mu sync.Mutex
	b  bytes.Buffer
}

func (b *synchronizedBuffer) Write(p []byte) (int, error) {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.b.Write(p)
}
func (b *synchronizedBuffer) String() string { b.mu.Lock(); defer b.mu.Unlock(); return b.b.String() }

type loginRuntime struct {
	mu                 sync.Mutex
	running            bool
	startedAt, endedAt string
	exitCode           any
	err                string
	output             synchronizedBuffer
	command            *exec.Cmd
}

var loginSession loginRuntime

func isAuthenticatedResult(r M) bool {
	if r["available"] != true || r["success"] != true {
		return false
	}
	text := strings.ToLower(fmt.Sprint(r["stdout"], "\n", r["stderr"]))
	for _, m := range []string{"not logged", "not authorized", "unauthorized", "log in", "login required"} {
		if strings.Contains(text, m) {
			return false
		}
	}
	return strings.TrimSpace(text) != ""
}
func accountStatus(c M) M {
	installation := cliInstallationStatus(c)
	if installation["installed"] != true {
		return M{"available": false, "authenticated": false, "message": installation["message"], "checked_at": now()}
	}
	r := runCLI(c, "license")
	return M{"available": r["available"], "authenticated": isAuthenticatedResult(r), "message": r["message"], "stdout": r["stdout"], "stderr": r["stderr"], "checked_at": now()}
}

func cliInstallationStatus(c M) M {
	parts := strings.Fields(str(c, "adguardvpn", "cli_command"))
	status := M{
		"installed": false, "available": false, "executable": nil,
		"version": nil, "checked_at": now(), "supported_architecture": supportedCLIArchitecture(),
		"pinned_version": pinnedCLIVersion, "install_command": "sh install/install-adguardvpn-cli.sh",
	}
	if len(parts) == 0 {
		status["message"] = "Команда AdGuard VPN CLI не настроена."
		return status
	}
	path, err := exec.LookPath(parts[0])
	if err != nil {
		status["message"] = fmt.Sprintf("AdGuard VPN CLI не установлен: '%s' не найден в PATH.", parts[0])
		return status
	}
	if absolute, absErr := filepath.Abs(path); absErr == nil {
		path = absolute
	}
	status["installed"] = true
	status["available"] = true
	status["executable"] = path
	version := cliVersion(c)
	status["runnable"] = version["success"] == true
	status["version"] = version["version"]
	status["message"] = "AdGuard VPN CLI установлен."
	if version["success"] != true {
		status["message"] = "AdGuard VPN CLI найден, но не запускается."
	}
	return status
}

func installCLI(c M) M {
	if !supportedCLIArchitecture() {
		return M{"success": false, "message": "Для архитектуры " + runtime.GOARCH + " нет закреплённой официальной сборки AdGuard VPN CLI.", "status": cliInstallationStatus(c)}
	}
	script := filepath.Join(baseDir, "install", "install-adguardvpn-cli.sh")
	if info, err := os.Stat(script); err != nil || info.IsDir() {
		return M{"success": false, "message": "Установщик AdGuard VPN CLI не найден.", "script_path": script, "status": cliInstallationStatus(c)}
	}
	r := runCommand(c, []string{"sh", script}, 900)
	r["script_path"] = script
	r["status"] = cliInstallationStatus(c)
	if r["success"] == true && section(r, "status")["runnable"] == true {
		r["message"] = "AdGuard VPN CLI установлен и готов к работе."
	} else if r["success"] == true {
		r["success"] = false
		r["message"] = "Установщик завершился, но CLI не найден или не запускается."
	}
	return r
}
func setupStatus(c M) M {
	s := section(c, "setup")
	return M{"completed": s["completed"] == true, "needs_setup": s["completed"] != true, "completed_at": s["completed_at"], "installation": cliInstallationStatus(c), "account": accountStatus(c), "login": currentLoginStatus(), "mode": str(c, "transparent_proxy", "mode"), "target_subnets": str(c, "transparent_proxy", "target_subnets"), "test_url": str(c, "vpn", "test_url"), "automation": section(c, "automation")}
}
func currentLoginStatus() M {
	loginSession.mu.Lock()
	defer loginSession.mu.Unlock()
	return M{"running": loginSession.running, "started_at": loginSession.startedAt, "ended_at": loginSession.endedAt, "exit_code": loginSession.exitCode, "error": loginSession.err, "output": loginSession.output.String()}
}

func startLogin(c M) M {
	loginSession.mu.Lock()
	if loginSession.running {
		loginSession.mu.Unlock()
		return currentLoginStatus()
	}
	parts := strings.Fields(str(c, "adguardvpn", "cli_command"))
	if len(parts) == 0 {
		loginSession.mu.Unlock()
		return M{"running": false, "error": "Команда adguardvpn-cli не настроена."}
	}
	if _, e := exec.LookPath(parts[0]); e != nil {
		loginSession.mu.Unlock()
		return M{"running": false, "error": fmt.Sprintf("Команда '%s' не найдена в PATH.", parts[0])}
	}
	cmd := exec.Command(parts[0], append(parts[1:], "login")...)
	cmd.Dir = baseDir
	cmd.Env = commandEnv()
	stdin, e := cmd.StdinPipe()
	if e != nil {
		loginSession.mu.Unlock()
		return M{"running": false, "error": e.Error()}
	}
	loginSession.output = synchronizedBuffer{}
	cmd.Stdout = &loginSession.output
	cmd.Stderr = &loginSession.output
	if e = cmd.Start(); e != nil {
		loginSession.mu.Unlock()
		return M{"running": false, "error": e.Error()}
	}
	loginSession.running = true
	loginSession.startedAt = now()
	loginSession.endedAt = ""
	loginSession.exitCode = nil
	loginSession.err = ""
	loginSession.command = cmd
	loginSession.mu.Unlock()
	go func() { time.Sleep(500 * time.Millisecond); _, _ = stdin.Write([]byte("b\n")) }()
	go func() {
		e := cmd.Wait()
		loginSession.mu.Lock()
		defer loginSession.mu.Unlock()
		loginSession.running = false
		loginSession.endedAt = now()
		if e != nil {
			loginSession.err = e.Error()
			if x, ok := e.(*exec.ExitError); ok {
				loginSession.exitCode = x.ExitCode()
			}
		} else {
			loginSession.exitCode = 0
		}
	}()
	go func() {
		time.Sleep(5 * time.Minute)
		loginSession.mu.Lock()
		defer loginSession.mu.Unlock()
		if loginSession.running && loginSession.command != nil && loginSession.command.Process != nil {
			_ = loginSession.command.Process.Kill()
			loginSession.err = "Время ожидания входа истекло."
		}
	}()
	return currentLoginStatus()
}

func completeSetup(c, p M) (M, error) {
	mode := strings.TrimSpace(fmt.Sprint(p["mode"]))
	if mode != "router-only" && mode != "transparent-redsocks" && mode != "tun-policy" && mode != "nfqueue" {
		return nil, fmt.Errorf("неизвестный режим работы: %s", mode)
	}
	tp := section(c, "transparent_proxy")
	tp["mode"] = mode
	tp["enabled"] = mode != "router-only"
	for _, k := range []string{"target_subnets", "destination_subnets", "destination_domains", "tun_interface"} {
		if v, ok := p[k]; ok {
			tp[k] = v
		}
	}
	if v := strings.TrimSpace(fmt.Sprint(p["test_url"])); v != "" && v != "<nil>" {
		section(c, "vpn")["test_url"] = v
	}
	if v := strings.TrimSpace(fmt.Sprint(p["expected_text"])); v != "" && v != "<nil>" {
		section(c, "vpn")["expected_text"] = v
	}
	if v, ok := p["automation_enabled"].(bool); ok {
		section(c, "automation")["enabled"] = v
	}
	if v, ok := p["check_interval"].(float64); ok {
		section(c, "automation")["check_interval"] = int(v)
	}
	validated, e := validateConfig(c)
	if e != nil {
		return nil, e
	}
	s := section(validated, "setup")
	s["completed"] = true
	s["completed_at"] = now()
	if e = saveConfig(validated); e != nil {
		return nil, e
	}
	notify()
	return M{"success": true, "message": "Первичная настройка завершена.", "config": validated, "setup": s}, nil
}

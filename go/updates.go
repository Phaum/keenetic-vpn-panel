package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"time"
)

const (
	panelRepoAPI     = "https://api.github.com/repos/Phaum/keenetic-vpn-panel/commits/go-version"
	cliReleaseAPI    = "https://api.github.com/repos/AdguardTeam/AdGuardVPNCLI/releases/latest"
	pinnedCLIVersion = "1.7.12"
)

var panelVersion = "dev"

type githubCommit struct {
	SHA    string `json:"sha"`
	Commit struct {
		Committer struct {
			Date string `json:"date"`
		} `json:"committer"`
	} `json:"commit"`
}
type githubRelease struct {
	TagName     string `json:"tag_name"`
	PublishedAt string `json:"published_at"`
	HTMLURL     string `json:"html_url"`
}

func githubJSON(url string, target any) error {
	client := &http.Client{Timeout: 12 * time.Second}
	req, e := http.NewRequest(http.MethodGet, url, nil)
	if e != nil {
		return e
	}
	req.Header.Set("Accept", "application/vnd.github+json")
	req.Header.Set("User-Agent", "keenetic-vpn-panel/"+panelVersion)
	resp, e := client.Do(req)
	if e != nil {
		return e
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("GitHub API: HTTP %d", resp.StatusCode)
	}
	return json.NewDecoder(resp.Body).Decode(target)
}

func localRevision() string {
	b, e := os.ReadFile(filepath.Join(projectDir, ".git", "HEAD"))
	if e != nil {
		if panelVersion != "" && panelVersion != "dev" {
			return panelVersion
		}
		return "unknown"
	}
	head := strings.TrimSpace(string(b))
	if strings.HasPrefix(head, "ref: ") {
		b, e = os.ReadFile(filepath.Join(projectDir, ".git", strings.TrimPrefix(head, "ref: ")))
		if e != nil {
			return "unknown"
		}
		head = strings.TrimSpace(string(b))
	}
	return head
}
func shortRevision(s string) string {
	if len(s) > 12 {
		return s[:12]
	}
	return s
}
func cliVersion(c M) M {
	r := runCLI(c, "--version")
	raw := strings.TrimSpace(fmt.Sprint(r["stdout"]))
	if raw == "" {
		raw = strings.TrimSpace(fmt.Sprint(r["stderr"]))
	}
	return M{"available": r["available"], "success": r["success"], "version": raw, "command": r["command"]}
}

func checkUpdates(c M) M {
	result := M{"checked_at": now(), "architecture": runtime.GOARCH, "pinned_cli_version": pinnedCLIVersion}
	local := localRevision()
	var commit githubCommit
	if e := githubJSON(panelRepoAPI, &commit); e != nil {
		result["panel"] = M{"current_version": panelVersion, "current_commit": shortRevision(local), "error": e.Error()}
	} else {
		known := local != "unknown"
		current := strings.HasPrefix(commit.SHA, local)
		result["panel"] = M{"current_version": panelVersion, "current_commit": shortRevision(local), "latest_commit": shortRevision(commit.SHA), "latest_date": commit.Commit.Committer.Date, "update_available": known && !current, "comparison_available": known}
	}
	localCLI := cliVersion(c)
	var release githubRelease
	if e := githubJSON(cliReleaseAPI, &release); e != nil {
		result["adguardvpn_cli"] = M{"local": localCLI, "error": e.Error(), "supported_architecture": supportedCLIArchitecture()}
	} else {
		latest := strings.TrimPrefix(strings.TrimSuffix(release.TagName, "-release"), "v")
		localText := strings.ToLower(fmt.Sprint(localCLI["version"]))
		result["adguardvpn_cli"] = M{"local": localCLI, "latest_version": latest, "latest_tag": release.TagName, "published_at": release.PublishedAt, "release_url": release.HTMLURL, "update_available": localCLI["available"] != true || !strings.Contains(localText, latest), "supported_architecture": supportedCLIArchitecture(), "pinned_version_current": latest == pinnedCLIVersion}
	}
	return result
}

func supportedCLIArchitecture() bool {
	switch runtime.GOARCH {
	case "amd64", "arm64", "arm", "mips", "mipsle":
		return true
	}
	return false
}

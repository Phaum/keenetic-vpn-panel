.PHONY: build test clean

PANEL_VERSION ?= $(shell git rev-parse --short=12 HEAD 2>/dev/null || echo dev)

build:
	go build -trimpath -ldflags="-s -w -X main.panelVersion=$(PANEL_VERSION)" -o keenetic-vpn-panel .

test:
	go test ./...

clean:
	rm -f keenetic-vpn-panel

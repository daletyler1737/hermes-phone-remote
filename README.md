# Phone Remote — Hermes desktop plugin

> English · [中文说明](README.zh-CN.md)

Adds a **Connect phone** entry to the Hermes desktop app: show a QR code, scan it with your
phone, and keep chatting with Hermes from the phone. A free, self-hosted stand-in for paid
"scan-to-pair + remote chat" features — **no extra service, no bespoke backend**; it reuses
the dashboard that already ships with Hermes.

Two modes:

| Mode | How the phone reaches the PC | Password needed |
|---|---|---|
| **LAN** | `http://<your-LAN-IP>:9119/`, same Wi-Fi | yes, log in once (session cookie persists) |
| **Internet** | Cloudflare quick tunnel, shows a public `https://…trycloudflare.com` address | **no** — scan-to-pair (one-shot token) |

## Status

**v0.2.0** (2026-09). Working, verified end-to-end: LAN login, scan-to-pair over a real
Cloudflare tunnel, byte-identical assets through the tunnel, and panel self-restart.
The stock dashboard's mobile portrait layout is not adapted (use landscape or "desktop site").

## How it works

- Phone page = the stock dashboard: `hermes dashboard --host 0.0.0.0 --port 9119`
- Chat transport = dashboard `/api/pty` WebSocket (ConPTY on Windows)
- Auth = dashboard `basic_auth` (cookie/token sessions — **not** HTTP Basic)
- **Internet mode** = Cloudflare quick tunnel (`cloudflared`, reused from DSH desktop if present)
  pointing at a small local reverse proxy (`tools/pair_proxy.py`, `127.0.0.1:9121`).
  The proxy serves `/pair?t=<token>` outside the dashboard's auth gate — which is the only way
  to implement scan-to-pair, since the auth plugin's public whitelist is just `/login`, `/auth/*`
  and static assets.
- Pairing state (`pending → approved → claimed`) lives in a per-user state file; claiming mints
  the same session cookie the dashboard would, so the phone lands **inside** the panel.
- QR = [qrcode-generator](https://github.com/kazuhikoarase/qrcode-generator) (MIT) inlined — desktop
  plugins may only import `@hermes/plugin-sdk`, `react`, `react/jsx-runtime`.

### Internet-mode safety rails

1. Address is random and unguessable.
2. Refuses to open a public link unless a dashboard password is set.
3. Two-step confirm (button flips to "confirm — reachable from the internet", auto-cancels after 8s).
4. **The tunnel dies on its own after 2 hours** (extendable), and there is a one-click stop.

## Install

```bash
python scripts/build_plugin.py --install     # build + copy into the desktop plugins dir
scripts\start_dashboard.bat                  # start a LAN-reachable dashboard
# once, as admin:
# New-NetFirewallRule -DisplayName "Hermes Phone Chat 9119" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 9119
# then in the app: Ctrl+K -> "Reload desktop plugins" -> Ctrl+K -> "Connect phone"
```

Credentials are never stored in this repo. Read the current ones with:

```bash
hermes config get dashboard.basic_auth
```

## Auth notes (these bite)

- The dashboard authenticates with **cookies/tokens, not HTTP Basic** — `curl -u` always 401s.
  The real endpoint is `POST /auth/password-login`
  (`{provider, username, password, next}` → `200 + Set-Cookie`).
- **`password_hash` takes precedence over the plaintext `password`** in `dashboard.basic_auth`.
  Changing only the plaintext leaves you with a 401. Set both:
  `hermes config set dashboard.basic_auth.password <new>` **and**
  `hermes config set dashboard.basic_auth.password_hash <scrypt$…>` (hash it with
  `plugins.dashboard_auth.basic.hash_password`), then restart the panel.
- Never hardcode a password into a script — passwords rotate.

## Host contracts worth remembering

- `render` belongs at the **top level** of `ctx.register({...})`, not inside `data`.
- Notifications use the object form: `host.notify({ kind, message })`.
- Sidebar nav items take `data: { path, label, codicon }`.
- Only the SDK, react and react/jsx-runtime may be imported; everything else gets inlined.
- Saving a plugin file does not reliably hot-reload a **newly added** folder — use
  `Reload desktop plugins` from the command palette.
- The QR SVG must stay black-on-white (never theme-tinted) or phones fail to scan.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Ctrl+K can't find "Connect phone" | plugin not scanned → run `Reload desktop plugins`; still missing → reload the window or restart the app |
| Phone can't open the address | dashboard running? (`curl http://127.0.0.1:9119/api/status` → 200) · firewall allows 9119? · same Wi-Fi? · LAN IP changed? |
| Login fails (401) | see *Auth notes* — `password_hash` is probably stale; note the dashboard has **no** Basic auth popup |
| Public link opens but the page is blank | reverse proxy must forward **blocking** (`recv`+`sendall`); the old non-blocking pump silently dropped backpressured writes (`unexpected EOF` in the cloudflared log) |
| Tunnel keeps dropping / Error 1033 | force IPv4 at the edge: `--edge-ip-version 4` (IPv6 edges time out behind fake-IP proxies) |
| "Restart panel" does nothing | the panel must not kill its own PID; use the detached respawn helper (`tools/dashboard_respawn.py`), which kills the old process only after the response is sent |
| Cramped layout on the phone | the stock dashboard is a desktop web UI; use landscape or "desktop site" |
| Dead after a reboot | the dashboard does not autostart → run `scripts\start_dashboard.bat` (or add a startup task) |

## Repo layout

```
src/plugin.template.js       maintainable source (QR library kept as /*__QR_INLINE__*/ placeholder)
vendor/qrcode-generator.js   MIT QR library, inlined at build time
scripts/build_plugin.py      template + vendor -> plugin.js  (--install copies into the plugins dir)
scripts/start_dashboard.bat  start a LAN-reachable dashboard
dashboard/plugin_api.py      backend mounted on the dashboard process
tools/pair_proxy.py          reverse proxy for scan-to-pair (Internet mode)
tools/dashboard_respawn.py   detached helper for restarting the panel from inside itself
tests/                       stdlib-only checks (tunnel TTL, pid-alive, password policy)
plugin.js                    build output (= what Hermes loads)
```

## JS runtimes

Build and verify scripts use only standard ESM plus `node:fs` — **no npm dependencies**,
so any of the three runtimes runs them unchanged:

```bash
node scripts/verify_qr.mjs
bun  scripts/verify_qr.mjs
deno run --allow-read scripts/verify_qr.mjs
```

## Development checks

```bash
node --check plugin.js                    # ESM syntax
python scripts/build_plugin.py --install  # build
bash tools/render-test/run.sh             # render regression (real react-dom render + assertions)
python tests/test_tunnel_ttl.py           # tunnel lifetime / claim logic, no real processes
python tests/test_pid_alive.py            # Windows-safe pid liveness
```

Backend changes only take effect after the panel restarts (it runs the code it imported at
startup) — use the plugin's own "Restart panel" button.

## Credits

- QR library: [qrcode-generator](https://github.com/kazuhikoarase/qrcode-generator) © Kazuhiko Arase, MIT, see `vendor/`.
- Approach inspired by DSH's `dsh-remote-web-ui` (point the QR at the official web GUI instead of
  writing a mobile page of your own).

## License

MIT. This repo contains **no credentials**; `.env` files and QR images (which embed your LAN
address) are gitignored.

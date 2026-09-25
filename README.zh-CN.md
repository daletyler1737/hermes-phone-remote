# 连接手机 · Phone Remote（Hermes 桌面版插件）

> [English](README.md) · 中文

在 Hermes 桌面版里加一个「连接手机」入口：**出二维码 → 手机扫码 → 在手机上继续和 Hermes 对话**。
对标同类付费的「扫码配对 + 手机远程聊天」，**零额外服务、零自研后端** —— 直接复用 Hermes 自带的 dashboard。

两种模式：

| 模式 | 手机怎么找到电脑 | 要不要密码 |
|---|---|---|
| **局域网** | `http://<你的局域网IP>:9119/`，同一个 Wi-Fi | 要，首次登录一次（之后靠会话 Cookie） |
| **互联网** | Cloudflare 临时隧道，给出公网 `https://…trycloudflare.com` 地址 | **不要** —— 扫码免密配对（一次性 token） |

## 状态

**v0.2.0**（2026-09）。已实测跑通：局域网登录、走真实 Cloudflare 隧道的扫码配对、经隧道资源字节级一致、
面板自重启。官方 dashboard 在手机竖屏下未做适配（建议横屏或浏览器「桌面版网站」）。

## 原理

- 手机页面 = Hermes 自带 dashboard：`hermes dashboard --host 0.0.0.0 --port 9119`
- 对话通道 = dashboard 的 `/api/pty` WebSocket（Windows 下走 ConPTY）
- 鉴权 = dashboard `basic_auth` 的会话 Cookie / token（**不是** HTTP Basic）
- **互联网模式** = 复用 `cloudflared`（本机装了 DSH desktop 就直接借用；没有则自行放置）指向本地反代
  `tools/pair_proxy.py`（`127.0.0.1:9121`）。反代在官方 auth gate 之外提供 `/pair?t=<token>` ——
  这是实现扫码免密的唯一途径，因为官方 auth 插件的公开白名单只有 `/login`、`/auth/*` 和静态资源。
- 配对状态 `pending → approved → claimed` 存本地状态文件；claim 时签发与官方同款的会话 Cookie，
  所以手机是**直接进到面板里**的。
- 二维码库 `qrcode-generator`（MIT）内联 —— 桌面插件只能 import `@hermes/plugin-sdk` / `react` /
  `react/jsx-runtime`，其他依赖必须内联。

### 互联网模式的安全闸

1. 地址随机、猜不到；
2. **没设面板密码就不给开公网链接**；
3. 两段式确认（按钮变「确认开启（外网可访问）」+ 警示，8 秒不点自动撤销）；
4. **隧道到点自断**（默认 2 小时，可延长），并可一键关闭。

## 安装

```bash
python scripts/build_plugin.py --install     # 构建并安装到桌面插件目录
scripts\start_dashboard.bat                  # 启动手机可访问的 dashboard
# 管理员 PowerShell 执行一次：
# New-NetFirewallRule -DisplayName "Hermes Phone Chat 9119" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 9119
# 然后：Ctrl+K → "Reload desktop plugins" → Ctrl+K → "连接手机"
```

凭据**不写进仓库**，查当前值：

```bash
hermes config get dashboard.basic_auth
```

## 登录这块的坑（必看）

- 面板认证走 **Cookie / token，不支持 HTTP Basic**（`curl -u` 永远 401）。真接口是
  `POST /auth/password-login`（`{provider, username, password, next}` → `200 + Set-Cookie`）。
- **`password_hash` 优先于明文 `password`**。只改明文不换 hash → 照样 401。要改就两个都改：
  `hermes config set dashboard.basic_auth.password <新密码>` **并且**
  `hermes config set dashboard.basic_auth.password_hash <scrypt$…>`（用
  `plugins.dashboard_auth.basic.hash_password` 现算），然后重启面板。
- 密码别硬编码进脚本 —— 会轮换。

## 故障排查

| 现象 | 原因与处理 |
|---|---|
| Ctrl+K 搜不到「连接手机」 | 插件没被扫描 → 执行 `Reload desktop plugins`；仍没有就重载窗口或重启桌面版 |
| 手机打不开地址 | dashboard 在跑吗（`curl http://127.0.0.1:9119/api/status` 应为 200）· 防火墙放行 9119 了吗 · 同一 Wi-Fi 吗 · 电脑 IP 变了吗 |
| 登录报 401 | 见上节 —— 多半是 `password_hash` 过期；注意面板**不会**弹 Basic 认证框 |
| 公网打得开但白屏 | 反代必须**阻塞式**转发（`recv` + `sendall`）；老的非阻塞实现会静默吞掉背压写（cloudflared 日志里的 `unexpected EOF`） |
| 隧道反复掉线 / Error 1033 | 强制 IPv4 边缘：`--edge-ip-version 4`（fake-IP 代理环境下 IPv6 边缘超时） |
| 「重启面板」没反应 | 面板不能杀自己那把 PID；用脱离式助手 `tools/dashboard_respawn.py`（应答完请求再杀旧进程并原地拉起） |
| 手机排版挤 | 官方 dashboard 是桌面 Web UI，竖屏未适配 → 横屏或「桌面版网站」 |
| 电脑重启后失效 | dashboard 不自启 → 跑 `scripts\start_dashboard.bat`（或做成开机任务） |

## 目录结构

```
src/plugin.template.js       可维护源码（QR 库处留 /*__QR_INLINE__*/ 占位符）
vendor/qrcode-generator.js   MIT 二维码库，构建时内联
scripts/build_plugin.py      模板 + vendor → plugin.js（--install 同步到插件目录）
scripts/start_dashboard.bat  启动局域网可访问的 dashboard
dashboard/plugin_api.py      挂在 dashboard 进程上的后端
tools/pair_proxy.py          扫码免密用的反代（互联网模式）
tools/dashboard_respawn.py   脱离式重启助手
tests/                       纯标准库自检（隧道 TTL、pid 探活、密码策略）
plugin.js                    构建产物（= Hermes 实际加载的文件）
```

## 开发自检

```bash
node --check plugin.js                    # ESM 语法
python scripts/build_plugin.py --install  # 构建
bash tools/render-test/run.sh             # 渲染回归（真 react-dom 渲染 + 断言）
python tests/test_tunnel_ttl.py           # 隧道存活/认领逻辑，不碰真进程
python tests/test_pid_alive.py            # Windows 下安全的 pid 探活
```

后端改动要点一次「重启面板」才生效（进程里跑的是启动时 import 的代码）。

## 致谢

- 二维码库：[qrcode-generator](https://github.com/kazuhikoarase/qrcode-generator) © Kazuhiko Arase，MIT，见 `vendor/`。
- 思路参考 DSH 的 `dsh-remote-web-ui`（二维码直指官方 Web GUI，不自研移动端页面）。

## 许可

MIT。**本仓库不含任何凭据**；`.env` 与二维码图片（含本机内网地址）均已在 `.gitignore` 中。

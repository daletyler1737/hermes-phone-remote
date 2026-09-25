/**
 * 连接手机 / Phone Remote — 扫码在手机上继续对话
 * ---------------------------------------------------------------------------
 * 目的：把「手机远程聊天」做成桌面版内置入口 —— 手机浏览器扫码即可继续对话。
 * 底层零自研：直接复用 Hermes 自带 dashboard（手机浏览器打开 http://<LAN-IP>:9119/），
 * 本插件只负责：① 出二维码 ② 给地址/账号/密码 ③ 一键打开本机面板 ④ 探测 IP 与服务状态。
 *
 * 入口三处：
 *   · Ctrl/⌘+K 搜「连接手机」（PALETTE_AREA）
 *   · 左侧栏导航「连接手机」（SIDEBAR_NAV_AREA）
 *   · 页面路由 /phone-connect（ROUTES_AREA）
 *
 * 注意：插件运行在受限沙箱里，只能 import '@hermes/plugin-sdk' / 'react' /
 * 'react/jsx-runtime'，且没有 JSX 编译 —— 所有元素都写成 jsx()/jsxs() 调用。
 * ctx.os 只开放 notify / openExternal / revealPath / writeClipboard，
 * 拿不到 shell，起服务那步只能靠外面的启动脚本（本页给按钮复制路径）。
 */
import {
  PALETTE_AREA,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  atom,
  Button,
  Input,
  Separator,
  host,
  useValue
} from '@hermes/plugin-sdk'
import { useEffect, useMemo, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

/* ─── 内联二维码编码器 ───────────────────────────────────────────────────────
   qrcode-generator v2.0.4 · MIT · (c) Kazuhiko Arase
   因为插件不能引外部 npm 包，这里把库源码内联（UMD 用伪 exports 包一层，
   使卷绕后的 factory 走 CommonJS 分支把构造函数交给 module.exports）。
   已验证：生成矩阵用 OpenCV 实扫，能解回原始 URL。
   ──────────────────────────────────────────────────────────────────────── */
const makeQr = (function () {
  const module = { exports: {} }
  const exports = module.exports
/*__QR_INLINE__*/
  return module.exports
})()

/* ─── 配置（持久化在插件自己的 storage 里）─────────────────────────────── */
const STORAGE_KEY = 'phoneRemote.cfg'
const DEFAULTS = {
  ip: '' /* 留空 = 自动探测局域网 IP；也可手填，如 192.168.1.10 */,
  port: '9119',
  user: '',
  pass: '',
  scriptDir: ''
}

const $cfg = atom({ ...DEFAULTS })
let store = null

function saveCfg(next) {
  $cfg.set(next)
  try {
    if (store) store.set(STORAGE_KEY, next)
  } catch {
    /* 持久化失败不影响本次会话使用 */
  }
}

/* ─── ctx.os 的防御式包装 ────────────────────────────────────────────────
   不同版本 API 名可能微调，这里做兜底，避免某个方法缺失就让整页失灵。 */
function osBridge(ctx) {
  const os = (ctx && ctx.os) || {}
  return {
    async copy(text) {
      try {
        if (os.writeClipboard) return Boolean(await os.writeClipboard(text))
      } catch {
        /* 落到下面的 false */
      }
      return false
    },
    notify(message, kind) {
      const payload = { kind: kind || 'info', message }
      // 宿主版本不同签名也不同：对象形式优先（已在官方 wallpaper 插件里确认），
      // 再退回 (message, kind)，最后放弃 —— 通知失败不该影响主流程。
      try {
        if (host && host.notify) {
          host.notify(payload)
          return
        }
      } catch {
        /* 试下一种 */
      }
      try {
        if (os.notify) os.notify(message, kind || 'info')
      } catch {
        /* 通知失败无所谓 */
      }
    },
    open(url) {
      try {
        if (os.openExternal) return Boolean(os.openExternal(url))
      } catch {
        /* 落到下面的 false */
      }
      return false
    },
    reveal(path) {
      try {
        if (os.revealPath) return Boolean(os.revealPath(path))
      } catch {
        /* 落到下面的 false */
      }
      return false
    }
  }
}

function go(path) {
  try {
    const nav = host && (host.navigate || host.open || host.go)
    if (typeof nav === 'function') return nav(path)
  } catch {
    /* 忽略，下面用提示兜底 */
  }
  return false
}

/* ─── 局域网 IP 自动探测 ─────────────────────────────────────────────────
   插件沙箱不给网络枚举 API，但 WebRTC 的 ICE 候选里带着本机内网地址；
   不依赖任何外部服务。拿不到就返回 null（用户仍可手填）。 */
/* 候选打分：真局域网网卡 > 虚拟网卡。
   192.168.x 最像家用/办公网（VirtualBox 占着 56/57 段，压低）；
   10.x 常见于办公网；172.16-31 是 Docker/Hyper-V/WSL 虚拟网卡的高发段。 */
function ipScore(ip) {
  if (!ip) return 0
  if (ip.indexOf('127.') === 0 || ip.indexOf('169.254.') === 0) return 0
  if (/^192\.168\./.test(ip)) return /^192\.168\.(56|57)\./.test(ip) ? 1 : 3
  if (/^10\./.test(ip)) return 2
  if (/^172\.(1[6-9]|2\d|3[01])\./.test(ip)) return 1
  return 1
}

function detectLanIp() {
  return new Promise(resolve => {
    let done = false
    let best = null
    const finish = value => {
      if (done) return
      done = true
      resolve(value)
    }
    // 超时兜底：交出目前最优的候选（可能仍是 null，用户还能手填）
    const timer = setTimeout(() => finish(best), 2500)
    try {
      const pc = new RTCPeerConnection({ iceServers: [] })
      pc.createDataChannel('probe')
      // ICE 候选会把所有网卡都报一遍，Hyper-V / WSL / VMware 的虚拟网卡（典型 172.26.x）
      // 经常排在真实网卡前面 —— 所以不能拿到第一个就用，要收完再挑分最高的。
      pc.onicecandidate = e => {
        const cand = e && e.candidate && e.candidate.candidate
        if (!cand) {
          // 候选收集结束：交出当前最优解
          clearTimeout(timer)
          try {
            pc.close()
          } catch {
            /* 无所谓 */
          }
          return finish(best)
        }
        const m = /([0-9]{1,3}([.][0-9]{1,3}){3})/.exec(cand)
        if (m && ipScore(m[1]) > ipScore(best)) best = m[1]
      }
      pc.createOffer()
        .then(o => pc.setLocalDescription(o))
        .catch(() => {
          clearTimeout(timer)
          finish(null)
        })
    } catch {
      clearTimeout(timer)
      finish(null)
    }
  })
}

/* ─── 面板改密码：借 Hermes 给插件的后端通道 ───────────────────────────────
   面板只能画界面，改 config.yaml / 重启服务都得下有后端。官方通道是
   ctx.rest(path) → /api/plugins/phone-remote/<path>（走桌面版自己的 IPC 桥，
   同源、免 CORS、自动带当前 profile），后端实现见仓库 dashboard/plugin_api.py。
   后端没装时 rest 会抛错 —— 这时给一句人话提示，不是白屏。 */
const PW_ALPHABET = 'abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789'
/* 刻意去掉 0 O 1 l i：手机小键盘上分不清，历史踩过「密码没敲错但就是登不上」。 */
function randomPassword(len) {
  const n = len || 16
  const buf = new Uint32Array(n)
  if (typeof crypto !== 'undefined' && crypto.getRandomValues) crypto.getRandomValues(buf)
  else for (let i = 0; i < n; i++) buf[i] = Math.floor(Math.random() * 4294967296)
  let out = ''
  for (let i = 0; i < n; i++) out += PW_ALPHABET[buf[i] % PW_ALPHABET.length]
  return out
}

function restBridge(ctx) {
  const fn = ctx && typeof ctx.rest === 'function' ? ctx.rest.bind(ctx) : null
  return async (path, opts) => {
    if (!fn) throw new Error('当前桌面版没给插件后端通道（ctx.rest 不存在）')
    return await fn(path, opts)
  }
}

/* 后端抛的错统一成一句话：FastAPI 的 detail 优先，其次 message。 */
function errText(e) {
  const d = (e && (e.detail || e.message)) || e
  return typeof d === 'string' ? d : JSON.stringify(d)
}

/* ─── 服务在线探测 ───────────────────────────────────────────────────────
   no-cors 模式：读不到状态码，但「连得上」就说明 9119 在监听。
   浏览器 CSP 若拦掉请求会走 catch，此时给「未检测到」而不是误报在线。 */
function useServiceStatus(url) {
  const [state, setState] = useState({ phase: 'checking', at: 0 })
  const [nonce, setNonce] = useState(0)
  useEffect(() => {
    let alive = true
    const probe = async () => {
      try {
        await fetch(url, { mode: 'no-cors', cache: 'no-store' })
        if (alive) setState({ phase: 'online', at: Date.now() })
      } catch {
        if (alive) setState({ phase: 'offline', at: Date.now() })
      }
    }
    setState({ phase: 'checking', at: Date.now() })
    probe()
    const id = setInterval(probe, 5000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [url, nonce])
  return [state, () => setNonce(n => n + 1)]
}

/* ─── 样式（一律走主题变量，深浅色自动跟随）───────────────────────────── */
const S = {
  root: {
    height: '100%',
    overflow: 'auto',
    padding: '20px 24px 28px',
    display: 'flex',
    flexDirection: 'column',
    gap: '16px',
    color: 'var(--ui-text-primary)',
    fontSize: '13px',
    lineHeight: 1.6
  },
  title: { fontSize: '16px', fontWeight: 600 },
  sub: { color: 'var(--ui-text-secondary)', fontSize: '12px' },
  card: {
    display: 'flex',
    gap: '20px',
    alignItems: 'flex-start',
    flexWrap: 'wrap',
    padding: '16px',
    borderRadius: '10px',
    background: 'var(--ui-bg-quaternary)',
    border: '1px solid color-mix(in srgb, var(--ui-stroke-secondary) 55%, transparent)'
  },
  col: { flex: '1 1 280px', minWidth: '260px', display: 'flex', flexDirection: 'column', gap: '10px' },
  row: { display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' },
  key: { color: 'var(--ui-text-secondary)', flex: '0 0 auto', width: '44px' },
  val: {
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
    fontSize: '12px',
    flex: '1 1 auto',
    minWidth: '120px',
    wordBreak: 'break-all'
  },
  steps: { margin: 0, paddingLeft: '18px', color: 'var(--ui-text-secondary)', display: 'flex', flexDirection: 'column', gap: '2px' },
  note: {
    display: 'flex',
    gap: '8px',
    padding: '8px 10px',
    borderRadius: '8px',
    background: 'var(--chrome-action-hover)',
    color: 'var(--ui-text-secondary)',
    fontSize: '12px'
  },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '10px', marginTop: '10px' },
  field: { display: 'flex', alignItems: 'center', gap: '8px' },
  fieldKey: { color: 'var(--ui-text-secondary)', width: '70px', flex: '0 0 auto' },
  statusBar: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    flexWrap: 'wrap',
    padding: '7px 10px',
    borderRadius: '8px',
    background: 'var(--chrome-action-hover)',
    fontSize: '12px'
  },
  dot: { width: '8px', height: '8px', borderRadius: '50%', flex: '0 0 auto' },
  card2: {
    display: 'flex',
    flexDirection: 'column',
    gap: '10px',
    padding: '14px 16px',
    borderRadius: '10px',
    background: 'var(--ui-bg-quaternary)',
    border: '1px solid color-mix(in srgb, var(--ui-stroke-secondary) 55%, transparent)'
  },
  cardTitle: { fontSize: '13px', fontWeight: 600 },
  tabs: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    flexWrap: 'wrap',
    padding: '4px',
    borderRadius: '10px',
    background: 'var(--chrome-action-hover)'
  },
  grid2: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '10px' },
  okMsg: { fontSize: '12px', color: 'var(--ui-accent)', whiteSpace: 'pre-wrap' },
  warnMsg: { fontSize: '12px', color: 'var(--ui-text-secondary)', whiteSpace: 'pre-wrap' },
}

/* ─── 二维码渲染：把矩阵按行合并成一条 SVG path ───────────────────────── */
function QrImage({ text, size }) {
  const { d, n } = useMemo(() => {
    const qr = makeQr(0, 'M')
    qr.addData(text)
    qr.make()
    const count = qr.getModuleCount()
    const parts = []
    for (let r = 0; r < count; r++) {
      let c = 0
      while (c < count) {
        if (qr.isDark(r, c)) {
          const start = c
          while (c < count && qr.isDark(r, c)) c++
          parts.push('M' + start + ' ' + r + 'h' + (c - start) + 'v1h-' + (c - start) + 'z')
        } else {
          c++
        }
      }
    }
    return { d: parts.join(''), n: count }
  }, [text])

  // 二维码必须白底黑块才能被扫（暗色模式下也不能反色），所以这里固定用白/黑，
  // 是功能性例外，不跟随主题配色。
  return jsx('div', {
    style: {
      background: '#ffffff',
      padding: '12px',
      borderRadius: '10px',
      lineHeight: 0,
      flex: '0 0 auto'
    },
    children: jsx('svg', {
      width: size,
      height: size,
      viewBox: '0 0 ' + n + ' ' + n,
      shapeRendering: 'crispEdges',
      children: jsx('path', { d, fill: '#000000' })
    })
  })
}

/* ─── 一行「标签 + 值 + 复制」────────────────────────────────────────── */
function Field({ label, value, secret, revealed, onToggle, onCopy }) {
  return jsxs('div', {
    style: S.row,
    children: [
      jsx('span', { style: S.key, children: label }),
      jsx('span', {
        style: S.val,
        children: secret && !revealed ? '••••••••' : value || '（未设置）'
      }),
      secret
        ? jsx(Button, {
            variant: 'text',
            size: 'inline',
            onClick: onToggle,
            children: revealed ? '隐藏' : '显示'
          })
        : null,
      jsx(Button, { variant: 'text', size: 'inline', onClick: onCopy, children: '复制' })
    ]
  })
}

/* ─── 页面主体 ───────────────────────────────────────────────────────── */
function PhonePage({ ctx }) {
  const cfg = useValue($cfg)
  const os = osBridge(ctx)
  const [revealed, setRevealed] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [draft, setDraft] = useState(null)
  const [ipHint, setIpHint] = useState(null)
  const rest = useMemo(() => restBridge(ctx), [ctx])
  const [pw, setPw] = useState('')
  const [pwShow, setPwShow] = useState(false)
  const [pwBusy, setPwBusy] = useState('')
  const [pwMsg, setPwMsg] = useState(null)
  const [svc, setSvc] = useState({ phase: 'loading' })
  const [log, setLog] = useState(null)
  const [mode, setMode] = useState('lan')                 // lan = 同一 WiFi；net = 公网隧道
  const [tun, setTun] = useState({ phase: 'loading' })    // 公网隧道状态


  const link = 'http://' + cfg.ip + ':' + cfg.port + '/'
  const localLink = 'http://127.0.0.1:' + cfg.port + '/'
  const d = draft || cfg

  const [status, recheck] = useServiceStatus('http://127.0.0.1:' + cfg.port + '/api/status')

  // 只在挂载时探测一次本机内网 IP；探测失败就什么都不显示，用户仍能手填。
  useEffect(() => {
    let alive = true
    detectLanIp().then(ip => {
      if (alive && ip && ip !== $cfg.get().ip) setIpHint(ip)
    })
    return () => {
      alive = false
    }
  }, [])

  const loadLog = () => rest('/login-log').then(d => setLog(d)).catch(() => {})

  // 公网隧道状态：后端自己起过就还在，面板重开也能认回来。
  const loadTun = () =>
    rest('/tunnel')
      .then(d => setTun({ phase: 'ok', data: d }))
      .catch(e => setTun({ phase: 'error', error: errText(e) }))

  // 挂载时问一次后端：账号 / 有没有设过密码 / 面板在不在跑。
  useEffect(() => {
    let alive = true
    rest('/status')
      .then(d => {
        if (alive) setSvc({ phase: 'ok', data: d })
      })
      .catch(e => {
        if (alive) setSvc({ phase: 'error', error: String((e && e.message) || e) })
      })
    loadLog()
    loadTun()
    return () => {
      alive = false
    }
  }, [rest])

  const edit = patch => setDraft({ ...d, ...patch })

  const sayPw = (text, ok) => setPwMsg({ text, ok })

  const doRandom = () => {
    const p = randomPassword(16)
    setPw(p)
    setPwShow(true)
    sayPw('已生成随机密码（去掉了容易看错的字符），点「确认更改」写入', true)
  }

  const doChange = async () => {
    if (pwBusy) return
    const value = pw.trim()
    if (!value) {
      sayPw('先填新密码，或点「随机密码」生成一个', false)
      return
    }
    setPwBusy('save')
    try {
      const res = await rest('/password', { method: 'POST', body: { password: value, username: cfg.user || undefined } })
      const user = (res && res.username) || cfg.user
      saveCfg({ ...cfg, user, pass: value }) // 面板上显示的密码跟着换新（明文只落在插件自己的 storage）
      setPw('')
      sayPw('已写入 config.yaml · 账号 ' + user + ' 的新密码要等「重启面板」之后才生效', true)
      os.notify('密码已更新，点「重启面板」生效', 'info')
    } catch (e) {
      sayPw('改密码失败：' + ((e && e.message) || e), false)
    } finally {
      setPwBusy('')
    }
  }

  const doRestart = async () => {
    if (pwBusy) return
    setPwBusy('restart')
    try {
      const res = await rest('/restart', { method: 'POST', body: { port: Number(cfg.port) || 9119 } })
      if (res && res.ok) {
        sayPw('面板已重启 · ' + (res.lan_url || '端口 ' + res.port) + '（清掉 ' + (res.killed || []).length + ' 个旧进程）', true)
        recheck()
        loadLog()
        os.notify('面板已重启', 'info')
      } else {
        sayPw('面板没起来：' + ((res && res.detail) || '未知原因') + ((res && res.tail) ? '\n' + res.tail : ''), false)
      }
    } catch (e) {
      sayPw('重启失败：' + ((e && e.message) || e), false)
    } finally {
      setPwBusy('')
    }
  }

  const tunUrl = (tun.data && tun.data.url) || ''
  const tunBusy = tun.phase === 'busy'

  const doTunnel = async action => {
    if (tunBusy) return
    setTun({ ...tun, phase: 'busy', action })
    try {
      const res = await rest('/tunnel', { method: 'POST', body: { action, port: Number(cfg.port) || 9119 } })
      setTun({ phase: 'ok', data: res })
      if (action === 'stop') {
        os.notify('公网链接已关闭', 'info')
      } else {
        os.notify('公网链接已开启：' + ((res && res.url) || ''), 'info')
      }
    } catch (e) {
      setTun({ phase: 'error', error: errText(e) })
      os.notify('公网链接操作失败', 'warn')
    }
  }

  const copyTun = async () => {
    if (!tunUrl) return
    const ok = await os.copy(tunUrl)
    os.notify(ok ? '已复制公网地址' : '复制失败，请手动选中地址', ok ? 'info' : 'warn')
  }

  const last = log && log.entries && log.entries.length ? log.entries[log.entries.length - 1] : null
  const logText = !log
    ? ''
    : last
      ? '最近一次手机登录：' + (last.ok ? '成功' : '失败') + (last.ip ? ' · ' + last.ip : '')
      : '还没有手机登录过'

  const svcText =
    svc.phase === 'loading'
      ? '正在读取面板状态…'
      : svc.phase === 'error'
        ? '面板后端还没挂上（重启一次 Hermes 桌面版即可）：' + svc.error
        : '账号 ' +
          svc.data.username +
          ' · ' +
          (svc.data.hash_set ? '已设置密码' : '还没设密码') +
          ' · 服务' +
          (svc.data.running ? '在跑' : '没在跑')

  const statusText =
    status.phase === 'online'
      ? '服务运行中 · ' + localLink
      : status.phase === 'checking'
        ? '正在检测服务…'
        : '未检测到服务（9119 没在跑，或浏览器拦了探测）'

  return jsxs('div', {
    style: S.root,
    children: [
      jsx('div', { style: S.title, children: '连接手机 · 扫码继续对话' }),

      jsxs('div', {
        style: S.statusBar,
        children: [
          jsx('span', {
            style: {
              ...S.dot,
              background:
                status.phase === 'online' ? 'var(--ui-accent)' : 'var(--ui-text-quaternary)'
            }
          }),
          jsx('span', { children: statusText }),
          jsx(Button, { variant: 'text', size: 'inline', onClick: recheck, children: '重新检测' })
        ]
      }),

      ipHint
        ? jsxs('div', {
            style: S.note,
            children: [
              jsx('span', {
                style: S.sub,
                children: '探测到本机局域网 IP 是 ' + ipHint + '，当前用的是 ' + (cfg.ip || '自动探测')
              }),
              jsx(Button, {
                variant: 'secondary',
                size: 'inline',
                onClick: () => {
                  saveCfg({ ...cfg, ip: ipHint })
                  setIpHint(null)
                  os.notify('已把局域网 IP 更新为 ' + ipHint, 'info')
                },
                children: '用这个'
              })
            ]
          })
        : null,

      jsxs('div', {
        style: S.tabs,
        children: [
          jsx(Button, {
            variant: mode === 'lan' ? 'secondary' : 'ghost',
            size: 'sm',
            onClick: () => setMode('lan'),
            children: '局域网模式'
          }),
          jsx(Button, {
            variant: mode === 'net' ? 'secondary' : 'ghost',
            size: 'sm',
            onClick: () => setMode('net'),
            children: '互联网模式'
          }),
          jsx('span', {
            style: S.sub,
            children:
              mode === 'lan'
                ? '手机和电脑连同一个 WiFi —— 最快、最稳'
                : '手机用 4G/5G 或别的网也能连 —— 走 Cloudflare 临时公网地址'
          })
        ]
      }),

      mode === 'net'
        ? jsxs('div', {
            style: S.card2,
            children: [
              jsxs('div', {
                style: S.row,
                children: [
                  jsx('span', { style: S.cardTitle, children: '公网链接' }),
                  jsx('span', {
                    style: S.sub,
                    children:
                      tun.phase === 'loading'
                        ? '正在读取…'
                        : tunBusy
                          ? tun.action === 'stop'
                            ? '正在关闭…'
                            : '正在创建（一般 5-15 秒）…'
                          : tunUrl
                            ? '已开启'
                            : '未开启'
                  })
                ]
              }),
              tunUrl
                ? jsxs('div', {
                    style: S.row,
                    children: [
                      jsx('span', { style: S.val, children: tunUrl }),
                      jsx(Button, { variant: 'outline', size: 'sm', onClick: copyTun, children: '复制' }),
                      jsx(Button, {
                        variant: 'ghost',
                        size: 'sm',
                        onClick: () => doTunnel('stop'),
                        children: tunBusy ? '处理中…' : '关闭'
                      })
                    ]
                  })
                : jsxs('div', {
                    style: S.row,
                    children: [
                      jsx(Button, {
                        variant: 'secondary',
                        size: 'sm',
                        onClick: () => doTunnel('start'),
                        children: tunBusy ? '创建中…' : '开启公网链接'
                      }),
                      jsx('span', { style: S.sub, children: '不开的时候，外网完全访问不到这台机器' })
                    ]
                  }),
              jsx('span', {
                style: S.sub,
                children:
                  '地址是临时的：面板一重启就换新的（Cloudflare 免费隧道就是这样），重开一次扫新码即可。登录用的还是上面那组账号密码。'
              }),
              tun.phase === 'error' ? jsx('div', { style: S.warnMsg, children: tun.error }) : null,
              tun.phase === 'error'
                ? jsx('span', {
                    style: S.sub,
                    children:
                      '本机需要有 cloudflared.exe（装过 DSH Desktop 就有自带的）；没有的话去 Cloudflare 官网下一个，改名 cloudflared.exe 放进插件目录再点一次。'
                  })
                : null
            ]
          })
        : null,

      jsxs('div', {
        style: S.card,
        children: [
          jsx(QrImage, { text: mode === 'net' ? tunUrl || link : link, size: 224 }),
          jsxs('div', {
            style: S.col,
            children: [
              jsxs('ol', {
                style: S.steps,
                children: [
                  jsx('li', {
                    children:
                      mode === 'net'
                        ? '手机（4G/5G 也行）扫左边的码，或直接打开下面的地址'
                        : '手机相机 / 微信「扫一扫」对准左边的二维码'
                  }),
                  jsx('li', { children: '首次打开输入下面这组账号密码，勾选「记住我」' }),
                  jsx('li', { children: '以后手机上就能聊天、切会话、看历史，和电脑端同一套会话' })
                ]
              }),
              jsx(Separator, {}),
              jsx(Field, {
                label: '地址',
                value: mode === 'net' ? tunUrl || '（还没开启公网链接）' : link,
                onCopy: async () => {
                  const target = mode === 'net' ? tunUrl : link
                  if (!target) {
                    os.notify('先在上面点「开启公网链接」', 'warn')
                    return
                  }
                  const ok = await os.copy(target)
                  os.notify(ok ? '已复制手机访问地址' : '复制失败，请手动选中地址', ok ? 'info' : 'warn')
                }
              }),
              jsx(Field, {
                label: '账号',
                value: cfg.user,
                onCopy: async () => {
                  const ok = await os.copy(cfg.user)
                  os.notify(ok ? '已复制账号' : '复制失败', ok ? 'info' : 'warn')
                }
              }),
              jsx(Field, {
                label: '密码',
                value: cfg.pass,
                secret: true,
                revealed,
                onToggle: () => setRevealed(!revealed),
                onCopy: async () => {
                  if (!cfg.pass) {
                    os.notify('还没填密码 —— 点下面「设置」填一次，或在设置里留空后手机端手动输', 'warn')
                    return
                  }
                  const ok = await os.copy(cfg.pass)
                  os.notify(ok ? '已复制密码' : '复制失败', ok ? 'info' : 'warn')
                }
              })
            ]
          })
        ]
      }),

      jsxs('div', {
        style: S.row,
        children: [
          jsx(Button, {
            variant: 'secondary',
            size: 'sm',
            onClick: () => {
              const ok = os.open(localLink)
              if (!ok) os.notify('无法自动打开浏览器，请手动访问 ' + localLink, 'warn')
            },
            children: '打开本机面板'
          }),
          jsx(Button, {
            variant: 'outline',
            size: 'sm',
            onClick: async () => {
              const ok = await os.copy(link)
              os.notify(ok ? '已复制 ' + link : '复制失败，请手动选中地址', ok ? 'info' : 'warn')
            },
            children: '复制手机地址'
          }),
          jsx(Button, {
            variant: 'ghost',
            size: 'sm',
            onClick: () => {
              const ok = os.reveal(cfg.scriptDir)
              if (!ok) os.notify('脚本目录：' + cfg.scriptDir, 'info')
            },
            children: '打开启动脚本文件夹'
          })
        ]
      }),

      jsxs('div', {
        style: S.card2,
        children: [
          jsxs('div', {
            style: S.row,
            children: [
              jsx('span', { style: S.cardTitle, children: '登录密码' }),
              jsx('span', { style: S.sub, children: svcText })
            ]
          }),
          jsxs('div', {
            style: S.grid2,
            children: [
              jsxs('div', {
                style: S.field,
                children: [
                  jsx('span', { style: S.fieldKey, children: '账号' }),
                  jsx(Input, {
                    size: 'sm',
                    value: d.user || '',
                    placeholder: 'admin',
                    onChange: e => edit({ user: e.target.value })
                  })
                ]
              }),
              jsxs('div', {
                style: S.field,
                children: [
                  jsx('span', { style: S.fieldKey, children: '新密码' }),
                  jsx(Input, {
                    size: 'sm',
                    type: pwShow ? 'text' : 'password',
                    value: pw,
                    placeholder: '至少 6 位',
                    onChange: e => setPw(e.target.value)
                  })
                ]
              })
            ]
          }),
          jsxs('div', {
            style: S.row,
            children: [
              jsx(Button, { variant: 'ghost', size: 'sm', onClick: doRandom, children: '随机密码' }),
              jsx(Button, {
                variant: 'secondary',
                size: 'sm',
                onClick: doChange,
                children: pwBusy === 'save' ? '写入中…' : '确认更改'
              }),
              jsx(Button, {
                variant: 'outline',
                size: 'sm',
                onClick: doRestart,
                children: pwBusy === 'restart' ? '重启中…' : '重启面板'
              }),
              jsx(Button, {
                variant: 'text',
                size: 'inline',
                onClick: () => setPwShow(!pwShow),
                children: pwShow ? '隐藏' : '显示'
              })
            ]
          }),
          logText ? jsx('span', { style: S.sub, children: logText }) : null,
          pwMsg ? jsx('div', { style: pwMsg.ok ? S.okMsg : S.warnMsg, children: pwMsg.text }) : null,
          jsx('span', {
            style: S.sub,
            children: '改完密码要点「重启面板」才生效 —— 密码是服务启动时读进内存的，重启前旧密码照样能登。'
          })
        ]
      }),

      jsxs('div', {
        style: S.note,
        children: [
          jsx('span', { children: '·' }),
          jsxs('span', {
            children: [
              jsx('b', { children: '状态是「未检测到」？' }),
              ' 说明后台服务没在跑 —— 点上面「重启面板」拉起来（等价于双击 ',
              jsx('code', { children: '启动手机网页-Start-Phone-Web.bat' }),
              '，服务监听 0.0.0.0:',
              cfg.port,
              '，防火墙入站规则 ',
              jsx('code', { children: 'Hermes Phone Chat ' + cfg.port }),
              ' 已放行）。'
            ]
          })
        ]
      }),

      jsxs('div', {
        children: [
          jsx(Button, {
            variant: 'text',
            size: 'inline',
            onClick: () => setShowSettings(!showSettings),
            children: (showSettings ? '▾' : '▸') + ' 设置（局域网 IP / 端口 / 显示用的账号密码）'
          }),
          showSettings
            ? jsxs('div', {
                children: [
                  jsxs('div', {
                    style: S.grid,
                    children: [
                      jsxs('div', {
                        style: S.field,
                        children: [
                          jsx('span', { style: S.fieldKey, children: '局域网 IP' }),
                          jsx(Input, {
                            size: 'sm',
                            value: d.ip,
                            placeholder: '192.168.x.x',
                            onChange: e => edit({ ip: e.target.value.trim() })
                          })
                        ]
                      }),
                      jsxs('div', {
                        style: S.field,
                        children: [
                          jsx('span', { style: S.fieldKey, children: '端口' }),
                          jsx(Input, {
                            size: 'sm',
                            value: d.port,
                            placeholder: '9119',
                            onChange: e => edit({ port: e.target.value.trim() })
                          })
                        ]
                      }),
                      jsxs('div', {
                        style: S.field,
                        children: [
                          jsx('span', { style: S.fieldKey, children: '账号' }),
                          jsx(Input, {
                            size: 'sm',
                            value: d.user,
                            placeholder: 'admin',
                            onChange: e => edit({ user: e.target.value })
                          })
                        ]
                      }),
                      jsxs('div', {
                        style: S.field,
                        children: [
                          jsx('span', { style: S.fieldKey, children: '密码' }),
                          jsx(Input, {
                            size: 'sm',
                            type: 'password',
                            value: d.pass,
                            placeholder: 'dashboard 密码',
                            onChange: e => edit({ pass: e.target.value })
                          })
                        ]
                      })
                    ]
                  }),
                  jsxs('div', {
                    style: { ...S.row, marginTop: '10px' },
                    children: [
                      jsx(Button, {
                        variant: 'secondary',
                        size: 'sm',
                        onClick: () => {
                          saveCfg({ ...cfg, ...d, scriptDir: d.scriptDir || DEFAULTS.scriptDir })
                          setDraft(null)
                          os.notify('已保存', 'info')
                        },
                        children: '保存'
                      }),
                      jsx(Button, {
                        variant: 'text',
                        size: 'inline',
                        onClick: () => setDraft({ ...DEFAULTS }),
                        children: '恢复默认'
                      }),
                      jsx('span', {
                        style: S.sub,
                        children: '这里的账号 / 密码只是本机备注（显示用）；真正生效的密码在上面「登录密码」里改。'
                      })
                    ]
                  })
                ]
              })
            : null
        ]
      })
    ]
  })
}

/* ─── 插件注册 ───────────────────────────────────────────────────────── */
export default {
  id: 'phone-remote',
  name: '连接手机',
  register(ctx) {
    // 加载探针：宿主把 renderer console 转发进 logs/desktop.log，
    // 这行日志是「插件确实被加载」的外部可验证证据。
    console.log('[phone-remote] loaded v3 — 连接手机插件已注册（状态灯 + IP 探测 + 面板改密码）')
    try {
      store = ctx.storage
    } catch {
      store = null
    }
    try {
      const saved = store ? store.get(STORAGE_KEY, null) : null
      if (saved && typeof saved === 'object') $cfg.set({ ...DEFAULTS, ...saved })
    } catch {
      /* 读不到就用默认值 */
    }

    const Page = () => jsx(PhonePage, { ctx })

    try {
    ctx.register({
      id: 'phoneRemote.page',
      area: ROUTES_AREA,
      data: { path: '/phone-connect' },
      render: Page
    })

    ctx.register({
      id: 'phoneRemote.nav',
      area: SIDEBAR_NAV_AREA,
      data: { path: '/phone-connect', label: '连接手机', codicon: 'device-mobile' }
    })

    ctx.register({
      id: 'phoneRemote.palette',
      area: PALETTE_AREA,
      data: {
        id: 'phoneRemote.palette',
        label: '连接手机',
        keywords: [
          '手机',
          '扫码',
          '二维码',
          '连接',
          '远程',
          '扫描',
          '配对',
          'phone',
          'qr',
          'mobile',
          'connect',
          'remote',
          'pair'
        ],
        detail: () => 'http://' + $cfg.get().ip + ':' + $cfg.get().port + '/',
        detailVariant: 'muted',
        run: () => {
          if (!go('/phone-connect')) {
            const ok = !!(ctx.os && ctx.os.notify)
            if (ok) ctx.os.notify('请在左侧栏点击「连接手机」', 'info')
          }
        }
      }
    })
    } catch (e) {
      // register 抛异常 = 插件整体加载失败，所以三个入口一起兜住。
      console.error('[phone-remote] register FAIL', e && e.stack ? e.stack : e)
      try {
        if (ctx.os && ctx.os.notify) ctx.os.notify('连接手机插件初始化失败：' + (e && e.message ? e.message : e))
      } catch {
        /* 连提示都发不出就只留日志 */
      }
    }
  }
}

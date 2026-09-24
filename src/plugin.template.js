/**
 * 连接手机 / Phone Remote — 扫码在手机上继续对话
 * ---------------------------------------------------------------------------
 * 目的：把「手机远程聊天」做成桌面版内置入口（替代 ekko 的扫码配对收费功能）。
 * 底层零自研：直接复用 Hermes 自带 dashboard（手机浏览器打开 http://<LAN-IP>:9119/），
 * 本插件只负责：① 出二维码 ② 给地址/账号/密码 ③ 一键打开本机面板。
 *
 * 入口三处：
 *   · Ctrl/⌘+K 搜「连接手机」（PALETTE_AREA）
 *   · 左侧栏导航「连接手机」（SIDEBAR_NAV_AREA）
 *   · 页面路由 /phone-connect（ROUTES_AREA）
 *
 * 注意：插件运行在受限沙箱里，只能 import '@hermes/plugin-sdk' / 'react' /
 * 'react/jsx-runtime'，且没有 JSX 编译 —— 所有元素都写成 jsx()/jsxs() 调用。
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
import { useMemo, useState } from 'react'
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
  ip: '192.168.1.34' /* ← 改成你的局域网 IP */,
  port: '9119',
  user: 'dale',
  pass: '',
  scriptDir: 'E:\\zip\\agent file big\\05_工具脚本\\hermes-phone'
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
  fieldKey: { color: 'var(--ui-text-secondary)', width: '70px', flex: '0 0 auto' }
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

  const link = 'http://' + cfg.ip + ':' + cfg.port + '/'
  const localLink = 'http://127.0.0.1:' + cfg.port + '/'
  const d = draft || cfg

  const edit = patch => setDraft({ ...d, ...patch })

  return jsxs('div', {
    style: S.root,
    children: [
      jsxs('div', {
        children: [
          jsx('div', { style: S.title, children: '连接手机 · 扫码继续对话' }),
          jsx('div', {
            style: S.sub,
            children: '手机和电脑连同一个 Wi-Fi 就行：不用装 App、不用数据线，也不花 ekko 那笔钱。'
          })
        ]
      }),

      jsxs('div', {
        style: S.card,
        children: [
          jsx(QrImage, { text: link, size: 224 }),
          jsxs('div', {
            style: S.col,
            children: [
              jsxs('ol', {
                style: S.steps,
                children: [
                  jsx('li', { children: '手机相机 / 微信「扫一扫」对准左边的二维码' }),
                  jsx('li', { children: '首次打开输入下面这组账号密码，勾选「记住我」' }),
                  jsx('li', { children: '以后手机上就能聊天、切会话、看历史，和电脑端同一套会话' })
                ]
              }),
              jsx(Separator, {}),
              jsx(Field, {
                label: '地址',
                value: link,
                onCopy: async () => {
                  const ok = await os.copy(link)
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
        style: S.note,
        children: [
          jsx('span', { children: '·' }),
          jsxs('span', {
            children: [
              jsx('b', { children: '「打开本机面板」打不开？' }),
              ' 说明后台服务没在跑 —— 双击脚本目录里的 ',
              jsx('code', { children: '启动手机网页-Start-Phone-Web.bat' }),
              ' 再试（服务监听 0.0.0.0:',
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
            children: (showSettings ? '▾' : '▸') + ' 设置（局域网 IP / 端口 / 账号 / 密码）'
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
                            placeholder: 'dale',
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
                        children: '密码用 hermes config get dashboard.basic_auth.password 查；手机端首次登录后浏览器会记住。'
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
    console.log('[phone-remote] loaded v1 — 连接手机插件已注册')
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

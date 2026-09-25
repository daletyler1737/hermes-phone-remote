// 真渲染一次面板：把编译产物挂到 react-dom 上跑，看它到底会不会炸、卡片在不在。
import { createElement } from 'react'
import ReactDOMServer from 'react-dom/server'
import plugin from './plugin.mjs'

const regs = []
const restCalls = []

const ctx = {
  storage: { get: () => null, set: () => {}, remove: () => {} },
  rest: (path, opts) => {
    restCalls.push(path)
    if (path === '/status')
      return Promise.resolve({
        username: 'admin',
        hash_set: true,
        plaintext_set: false,
        session_ttl_seconds: 43200,
        min_length: 6,
        port: 9119,
        running: true,
        lan_ip: '192.168.1.10',
        url: 'http://192.168.1.10:9119/'
      })
    if (path === '/tunnel')
      return Promise.resolve({
        ok: true, running: true, url: 'https://demo-example-abc.trycloudflare.com', pid: 1234, port: 9119
      })
    if (path === '/pair')
      return Promise.resolve({
        ok: true,
        status: 'pending',
        token_tail: '…AbCd',
        ip: '192.168.1.85',
        ua: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Safari/604.1',
        url: 'https://demo-example-abc.trycloudflare.com/pair?t=demo',
        expires_at: Date.now() / 1000 + 600,
        proxy: true,
        port: 9121,
        ttl_seconds: 600,
        tunnel: 'https://demo-example-abc.trycloudflare.com',
        tunnel_running: true
      })
    if (path === '/login-log')
      return Promise.resolve({ path: 'logs/dashboard-auth.log', entries: [{ ok: true, ip: '192.168.1.85', line: 'login_success ip=192.168.1.85' }] })
    return Promise.resolve({ ok: true })
  },
  os: {
    notify: (...a) => console.log('[ctx.os.notify]', ...a),
    openExternal: (...a) => console.log('[ctx.os.openExternal]', ...a),
    revealPath: (...a) => console.log('[ctx.os.revealPath]', ...a),
    writeClipboard: (...a) => console.log('[ctx.os.writeClipboard]', ...a)
  },
  register: (r) => regs.push(r),
  registerCommand: (r) => regs.push(r)
}

console.log('== export 形状 ==', Object.keys(plugin))
plugin.register(ctx)
console.log('== 注册条目 ==', regs.map((r) => r.id + '@' + r.area).join(', '))

const page = regs.find((r) => r.id === 'phoneRemote.page')
if (!page || typeof page.render !== 'function') throw new Error('没有注册页面组件')

let html = ''
try {
  html = ReactDOMServer.renderToStaticMarkup(createElement(page.render))
} catch (e) {
  console.log('!! 渲染炸了:', (e && e.stack) || e)
  process.exit(1)
}

console.log('== 渲染体积 ==', html.length, 'chars')
const want = [
  '连接手机', '重新检测', '打开本机面板', '复制手机地址', '打开启动脚本文件夹',
  '登录密码', '新密码', '随机密码', '确认更改', '重启面板',
  '改完密码要点', '入站规则'
]
const missing = want.filter((k) => !html.includes(k))
for (const k of want) console.log('  ', k.padEnd(10), html.includes(k) ? '✓ 在' : '✗ 缺')
if (missing.length) {
  console.log('!! 面板少了这些字样:', missing.join(' / '))
  process.exit(1)      // 测试要能失败，不然等于没测
}
console.log('== 明文密码不该出现在 markup ==', /password_hash/.test(html) ? '✗ 泄漏' : '✓ 没有')
console.log('== 面板 markup 摘要 ==')
console.log(html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').slice(0, 1400))

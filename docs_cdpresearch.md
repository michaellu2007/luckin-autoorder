# CDP 逆向研究日志（瑞幸小程序）

## 已确认的事实（2026-10-29 凌晨）

1. **接口加密**：用户相关 API（优惠券/订单/下单/支付）走 `capisk/capi.lkcoffee.com`，
   请求体 `cid=<城市id>&q=<密文>&dk=1&sign=<签名>`，响应为 `EAT879...` 密文信封，
   鉴权不在请求头（只有设备 uid cookie）。菜单/首页是明文 JSON。
   → 纯 HTTP 重放对下单不可行，除非逆向其 JS 加密（暂不必要）。
2. **WMPFDebugger 可用**：`npx tsx src/index.ts --auto-detect` 自动适配 WMPF 25799
   （微信 4.1.8.28），hook 后小程序运行时连调试服务（9421），CDP 客户端走 62000 代理。
   代理是纯广播桥：无会话路由，默认会话=当前小程序页面上下文。
3. **已打通**：62000 上 Network 域监听可实时抓小程序全部请求（scripts/cdp_capture.py，
   已抓 104 条）；Target.getTargets 可列出 25 个 target；页面/webview target 可
   attach + sessionId 求值；默认会话 Runtime.evaluate 可执行。
4. **未打通**：逻辑层（appservice，wx API 所在）——15 个匿名 worker attach 全部
   超时（3s 超时，长超时版 scripts/cdp_appservice.py 已备好未跑）；
   wxalite 子视图（真 UI）body 为空（22 元素，lite 运行时壳，内容可能在别处渲染）。
5. **生命周期坑**：WeChatAppEx.exe 会退出（小程序全关后）；hook 绑定旧 pid，运行时
   重生后必须重启 WMPFDebugger 重挂；小程序实例须在 hook 后（重）打开才会连调试服务。
   微信重启可能需要手机确认登录——避免杀 Weixin.exe。

## 接力剧本（无人值守轮询）

每轮按序检查，满足即执行，否则原地等待下一轮：

1. `tasklist | grep -ci wechatappex` == 0 → 本轮结束（等用户打开任意小程序）
2. WMPFDebugger 未运行（62000/9421 无监听）→ 清端口残留 → 后台重启
   `npx tsx src/index.ts --auto-detect`（在 WMPFDebugger 目录）→ 本轮结束
3. 日志无 "miniapp client connected" → 本轮结束（等用户打开/刷新瑞幸小程序）
4. 已连接 → `python scripts/cdp_appservice.py`（15s 长超时逐个探测 worker）
5. 找到逻辑层（eval 返回 typeof wx == object）后：
   - `JSON.stringify(wx.getStorageInfoSync())` 拿全部键名
   - 逐键读值（token/uid/门店/用户信息），**只读**
   - 定位订单列表函数：在逻辑层 eval 搜索 app 的请求封装
     （如 `typeof __wxConfig`、webpack chunk、全局 request 函数名），
     或直接调用页面栈里订单页的数据加载函数（getCurrentPages）
   - 拉到订单列表 JSON 即为「读订单」达成；下单方法只记录链路（接口/函数/参数），
     **绝不执行**
6. 发现写回本文件；每轮结尾 CronCreate 一份 1 分钟后的接力任务
   （recurring=false, delayMinutes=1），全部研究清楚才停。

## 红线

只读研究。严禁真实下单、严禁支付、严禁触发任何写操作接口。


## 研究完成（2026-10-29）

### 最终结论

1. **逻辑层接通方法**：worker target 的 Target.attachToTarget 在此桥上不可用（会话
   不路由）；正确做法是 `Runtime.enable` 列出执行上下文，appservice = 含
   `typeof getCurrentPages === 'function'` 的 contextId（本次为 4）。之后所有
   `Runtime.evaluate` 带 `contextId` 即可在逻辑层执行任意 JS。
2. **凭证与用户数据**：`wx.getStorageInfoSync()` 可读全部 storage：
   `lk_uid`（完整登录凭证）、`lk_userId`、`lk_loginMobile`、`lk_prevDeptId`
   （最近门店）、资产缓存（券数/咖啡钱包余额）等。
3. **订单读取（已验证）**：给 `wx.request` 挂只读包装（记录 url/参数、包装 success
   回调记录解密后响应），再 `wx.navigateTo('/pages/index/order/list')`，
   订单列表接口为明文 `GET /resource/core/v2/order/list`，完整数据也可从
   `getCurrentPages().slice(-1)[0].data.listData` 直接读。
4. **下单方法（已记录，未执行）**：下单链路 = 菜单 `/resource/core/v3/product/menu`
   （明文）→ 确认单页 `subComponents/confirm` → 创建订单（加密接口）→ 支付。
   直接 HTTP 重放不可行；自动化路径 = CDP 驱动小程序自身（它自带加解密），
   可用同样的 wx.request 包装观察 createOrder 请求参数。
5. **运行要求**：研究时需小程序保持打开 + WMPFDebugger 运行（hook 绑定 pid，
   运行时重启需重挂）。无人值守自动化应基于此流程封装。

### 红线

全程只读。未下单、未支付、未调用任何写接口。wx.request 包装仅记录，不影响行为。

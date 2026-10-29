"""一键抓取下单全链路（创建订单 + 支付的真实接口参数）。

用法（想下单的那个早上）：
  1. python scripts/capture_order_flow.py
  2. 脚本自动：启动 WMPFDebugger → 等你打开瑞幸小程序 → 装全量监听器
  3. 你像平常一样手动下单、免密支付
  4. 脚本检测到创建订单/支付的请求后，自动保存 logs/order_flow_<日期>.json 并退出

抓全之后把文件发给助手，就能把自动下单做成无人值守版。
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import websocket

ROOT = Path(__file__).resolve().parent.parent
DEBUGGER_DIR = ROOT.parent / "WMPFDebugger"
CDP = "ws://127.0.0.1:62000"
WATCH = ("v1/order/create", "v2/pay/topay")          # 检测到这些关键词即认为下单完成
TIMEOUT_MIN = 40                              # 最长等待下单的时间


def log(msg):
    print(time.strftime("[%H:%M:%S]") + " " + msg, flush=True)


def debugger_running():
    import socket
    s = socket.socket()
    s.settimeout(1)
    try:
        s.connect(("127.0.0.1", 62000))
        s.close()
        return True
    except OSError:
        return False


def start_debugger():
    log("启动 WMPFDebugger（需已打开微信，首次注入约 30 秒）…")
    proc = subprocess.Popen(
        ["npx", "tsx", "src/index.ts", "--auto-detect"],
        cwd=str(DEBUGGER_DIR),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        shell=True, text=True, encoding="utf-8", errors="replace")
    for _ in range(60):
        if debugger_running():
            log("调试代理已就绪")
            return proc
        time.sleep(2)
    raise RuntimeError("调试代理启动失败，看上方输出")


def cdp():
    return websocket.create_connection(CDP, timeout=15, suppress_origin=True)


def attach(ws):
    """attach 瑞幸 AppIndex，返回 (send函数, sessionId, 上下文探测结果)。"""
    ids = iter(range(1, 10000))

    def send(method, params=None, sid=None):
        i = next(ids)
        msg = {"id": i, "method": method, "params": params or {}}
        if sid:
            msg["sessionId"] = sid
        ws.send(json.dumps(msg))
        return i

    i = send("Target.getTargets")
    sid = None
    end = time.time() + 10
    while time.time() < end and not sid:
        try:
            m = json.loads(ws.recv())
        except websocket.WebSocketTimeoutException:
            continue
        if m.get("id") == i:
            for t in m["result"]["targetInfos"]:
                if "wx21c7506e98a2fe75" in t["url"] and t["type"] == "page":
                    a = send("Target.attachToTarget",
                             {"targetId": t["targetId"], "flatten": True})
                    while time.time() < end:
                        try:
                            m2 = json.loads(ws.recv())
                        except websocket.WebSocketTimeoutException:
                            break
                        if m2.get("id") == a:
                            sid = m2.get("result", {}).get("sessionId")
                            break
    if not sid:
        raise RuntimeError("attach 失败：小程序没开？")
    send("Runtime.enable", sid=sid)
    ctxs = set()
    end = time.time() + 10
    while time.time() < end:
        try:
            m = json.loads(ws.recv())
        except websocket.WebSocketTimeoutException:
            continue
        if m.get("method") == "Runtime.executionContextCreated":
            ctxs.add(m["params"]["context"]["id"])

    def ev(expr, ctx=None, timeout=12):
        params = {"expression": expr, "returnByValue": True}
        if ctx:
            params["contextId"] = ctx
        j = send("Runtime.evaluate", params, sid=sid)
        ws.settimeout(timeout)
        while True:
            try:
                m = json.loads(ws.recv())
            except websocket.WebSocketTimeoutException:
                return None
            if m.get("id") == j:
                res = m.get("result", {})
                if res.get("exceptionDetails"):
                    return None
                return res.get("result", {}).get("value")

    return send, sid, ev, ctxs


HOOK = """(function(){
  globalThis.__cap2 = globalThis.__cap2 || [];
  if (globalThis.__reqHooked2) return 'already';
  var orig = wx.request.bind(wx);
  wx.request = function(opt){
    var entry = {ts: Date.now(), method: opt.method || 'GET', url: opt.url,
                 data: typeof opt.data === 'object' ? JSON.stringify(opt.data) : String(opt.data||''),
                 resp: null, err: null};
    globalThis.__cap2.push(entry);
    var os = opt.success;
    if (typeof os === 'function') opt.success = function(res){ try { entry.resp = String(JSON.stringify(res.data)).slice(0,60000); } catch(e){} return os(res); };
    var of = opt.fail;
    if (typeof of === 'function') opt.fail = function(er){ entry.err = String(er && er.errMsg); return of(er); };
    return orig(opt);
  };
  globalThis.__reqHooked2 = true;
  return 'ok';
})()"""


def main():
    proc = None
    if not debugger_running():
        proc = start_debugger()

    log("等待瑞幸小程序连接调试服务（打开/刷新一下小程序）…")
    ws = None
    send = sid = ev = ctxs = None
    for attempt in range(30):
        try:
            ws = cdp()
            send, sid, ev, ctxs = attach(ws)
            break
        except Exception as e:
            try:
                ws.close()
            except Exception:
                pass
            time.sleep(5)
    if not ev:
        raise RuntimeError("连不上小程序调试通道")
    log("已连上小程序")

    app_ctx = None
    for cid in sorted(ctxs):
        if ev("String(typeof wx)+':'+String(typeof getCurrentPages)", cid, timeout=6) == "object:function":
            app_ctx = cid
    if not app_ctx:
        raise RuntimeError("没找到逻辑层上下文")

    state = ev("String(globalThis.__cap2?globalThis.__cap2.length:'none')", app_ctx, timeout=8)
    log(f"安装全量监听器（此前状态 {state}）…")
    ev(HOOK, app_ctx, timeout=10)
    log("✅ 监听器就位。现在像平常一样下单、免密支付即可。")
    log(f"   检测到创建订单/支付请求后自动保存并退出（最长等 {TIMEOUT_MIN} 分钟，Ctrl+C 随时保存）")

    out = ROOT / "logs" / f"order_flow_{time.strftime('%Y%m%d')}.json"
    out.parent.mkdir(exist_ok=True)
    try:
        end = time.time() + TIMEOUT_MIN * 60
        while time.time() < end:
            time.sleep(10)
            cap = ev("JSON.stringify(globalThis.__cap2||[])", app_ctx, timeout=15)
            if not cap:
                log("监听数据读不到（运行时重启？），尝试重连…")
                try:
                    ws.close()
                except Exception:
                    pass
                ws = cdp()
                send, sid, ev, ctxs = attach(ws)
                app_ctx = None
                for cid in sorted(ctxs):
                    if ev("String(typeof wx)+':'+String(typeof getCurrentPages)", cid, timeout=6) == "object:function":
                        app_ctx = cid
                if app_ctx:
                    ev(HOOK, app_ctx, timeout=10)
                continue
            try:
                entries = json.loads(cap)
            except Exception:
                continue
            hits = [e for e in entries
                    if any(k in e["url"].lower() for k in WATCH) and e.get("resp")]
            if hits:
                out.write_text(json.dumps(entries, ensure_ascii=False, indent=1),
                               encoding="utf-8")
                log(f"🎯 捕获到下单链路（{len(hits)} 条关键请求），已保存 {out.name}")
                for e in hits:
                    log(f"   {e['method']} {e['url'][:90]}")
                return
    except KeyboardInterrupt:
        pass
    finally:
        cap = None
        try:
            cap = ev("JSON.stringify(globalThis.__cap2||[])", app_ctx, timeout=10)
        except Exception:
            pass
        if cap and cap not in ("None", "null"):
            out.write_text(json.dumps(json.loads(cap), ensure_ascii=False, indent=1),
                           encoding="utf-8")
            log(f"已保存当前捕获到 {out.name}")
        try:
            ws.close()
        except Exception:
            pass
        # 调试器保持运行，供后续轮询使用
    log("超时未等到下单，退出。")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()

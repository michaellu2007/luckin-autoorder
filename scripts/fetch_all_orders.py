"""抓取瑞幸完整订单历史（分页循环到 hasNext=False）。

前提：瑞幸小程序已打开且停在「我的订单」页，WMPFDebugger 运行中。
用法：python scripts/fetch_all_orders.py
产出：logs/orders_full.json（全量订单）
"""

import json
import sys
import time
from pathlib import Path

import websocket

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "logs" / "orders_full.json"


def connect():
    ws = websocket.create_connection("ws://127.0.0.1:62000", timeout=15,
                                     suppress_origin=True)
    _id = [0]

    def send(method, params=None, sid=None):
        _id[0] += 1
        msg = {"id": _id[0], "method": method, "params": params or {}}
        if sid:
            msg["sessionId"] = sid
        ws.send(json.dumps(msg))
        return _id[0]

    i = send("Target.getTargets")
    ws.settimeout(12)
    while True:
        m = json.loads(ws.recv())
        if m.get("id") == i:
            break
    luck = [t for t in m["result"]["targetInfos"] if "wx21c7506e98a2fe75" in t["url"]]
    if not luck:
        raise RuntimeError("瑞幸小程序未连接（打开小程序后重试）")
    a = send("Target.attachToTarget",
             {"targetId": luck[0]["targetId"], "flatten": True})
    while True:
        m = json.loads(ws.recv())
        if m.get("id") == a:
            sid = m["result"]["sessionId"]
            break
    send("Runtime.enable", sid=sid)
    ctxs = set()
    end = time.time() + 8
    while time.time() < end:
        try:
            m = json.loads(ws.recv())
        except websocket.WebSocketTimeoutException:
            continue
        if m.get("method") == "Runtime.executionContextCreated":
            ctxs.add(m["params"]["context"]["id"])
    app = None
    ws.settimeout(6)
    for cid in sorted(ctxs):
        j = send("Runtime.evaluate",
                 {"expression": "String(typeof wx)+':'+String(typeof getCurrentPages)",
                  "returnByValue": True, "contextId": cid})
        while True:
            try:
                m = json.loads(ws.recv())
            except websocket.WebSocketTimeoutException:
                break
            if m.get("id") == j:
                if m.get("result", {}).get("result", {}).get("value") == "object:function":
                    app = cid
                break
        if app:
            break
    if not app:
        raise RuntimeError("没找到逻辑层上下文")
    return ws, send, sid, app


def ev(ws, send, sid, app, expr, timeout=15):
    j = send("Runtime.evaluate", {"expression": expr, "returnByValue": True,
                                  "contextId": app}, sid=sid)
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


def main():
    ws, send, sid, app = connect()
    print("已连上小程序，开始分页抓取…")

    def snapshot():
        r = ev(ws, send, sid, app,
               """(function(){
                 var p = getCurrentPages().slice(-1)[0]; var d = p.data;
                 var n = 0;
                 (d.listData||[]).forEach(function(g){ n += (g||[]).length; });
                 return JSON.stringify({count:n, hasNext:d.hasNext,
                   route:p.route});
               })()""", timeout=15)
        try:
            return json.loads(r)
        except Exception:
            return {"count": 0, "hasNext": None, "route": "?"}

    if "order/list" not in str(snapshot().get("route")):
        print("⚠️ 当前不在订单列表页，先导航过去…")
        ev(ws, send, sid, app, "wx.navigateTo({url:'/pages/index/order/list'})", timeout=10)
        time.sleep(4)

    st = snapshot()
    stuck = 0
    for round_ in range(80):
        print(f"  轮 {round_+1}: {st.get('count')} 单, hasNext={st.get('hasNext')}",
              flush=True)
        if st.get("hasNext") is False:
            break
        before = st.get("count", 0)
        ev(ws, send, sid, app,
           "try{getCurrentPages().slice(-1)[0].onReachBottom()}catch(e){}",
           timeout=12)
        time.sleep(2.5)
        st = snapshot()
        stuck = stuck + 1 if st.get("count", 0) == before else 0
        if stuck >= 4:
            print("连续 4 轮无增长，视为已到底")
            break

    raw = ev(ws, send, sid, app,
             "JSON.stringify(getCurrentPages().slice(-1)[0].data.listData)",
             timeout=30)
    data = json.loads(raw)
    flat = [o for grp in data for o in (grp if isinstance(grp, list) else [grp])]
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    times = [o["orderTime"] for o in flat if o.get("orderTime")]
    print(f"\n✅ 全量 {len(flat)} 单 → {OUT.name}")
    if times:
        print(f"   范围：{min(times)} ~ {max(times)}")
    ws.close()


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()

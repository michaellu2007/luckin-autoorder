"""找到瑞幸小程序逻辑层（appservice worker）并读取 storage。

前置：WMPFDebugger 已启动且瑞幸小程序已打开（调试服务显示 miniapp client connected）。
用法：python scripts/cdp_appservice.py
只读操作：不创建订单、不支付。
"""

import json
import sys

import websocket

CDP_URL = "ws://127.0.0.1:62000"


class Cdp:
    def __init__(self, timeout=8):
        self.ws = websocket.create_connection(CDP_URL, timeout=timeout,
                                              suppress_origin=True)
        self._id = 0

    def call(self, method, params=None, sid=None, timeout=None):
        self._id += 1
        msg = {"id": self._id, "method": method, "params": params or {}}
        if sid:
            msg["sessionId"] = sid
        self.ws.send(json.dumps(msg))
        self.ws.settimeout(timeout or 8)
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == self._id:
                if "error" in m:
                    raise RuntimeError(f"{method}: {m['error']}")
                return m
            # 事件直接丢弃（会打印关键事件）

    def eval(self, expr, sid, timeout=10):
        r = self.call("Runtime.evaluate",
                      {"expression": expr, "returnByValue": True,
                       "awaitPromise": True},
                      sid=sid, timeout=timeout)
        res = r.get("result", {})
        if res.get("exceptionDetails"):
            raise RuntimeError(f"eval 异常: {json.dumps(res['exceptionDetails'])[:200]}")
        return res.get("result", {}).get("value")


def main():
    cdp = Cdp()
    targets = cdp.call("Target.getTargets")["result"]["targetInfos"]
    workers = [t for t in targets if t["type"] == "worker"]
    print(f"共 {len(targets)} target，其中 {len(workers)} 个 worker，逐个长超时探测…")

    for i, t in enumerate(workers):
        try:
            r = cdp.call("Target.attachToTarget",
                         {"targetId": t["targetId"], "flatten": True},
                         timeout=15)
        except Exception as e:
            print(f"[{i}] attach 超时/失败")
            continue
        sid = r.get("result", {}).get("sessionId")
        if not sid:
            print(f"[{i}] attach 无 sessionId")
            continue
        try:
            val = cdp.eval("typeof wx + '|' + typeof getCurrentPages + '|'"
                           "+ (typeof __wxAppCode__ !== 'undefined')", sid, timeout=15)
            print(f"[{i}] -> {val}")
            if val and val.startswith("object"):
                print(f"  *** [{i}] 就是逻辑层！sessionId={sid}")
                keys = cdp.eval("JSON.stringify(wx.getStorageInfoSync())", sid)
                print("  storage info:", keys)
                return
        except Exception as e:
            print(f"[{i}] eval 失败: {str(e)[:120]}")
    print("没有找到逻辑层 worker。")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()

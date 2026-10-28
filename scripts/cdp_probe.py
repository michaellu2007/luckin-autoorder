"""CDP 探测：找到瑞幸小程序的 appservice 上下文并测试 wx 能力。

用法：python scripts/cdp_probe.py
"""

import json
import sys

import websocket

CDP_URL = "ws://127.0.0.1:62000"
LUCKIN_APPID = "wx21c7506e98a2fe75"


class Cdp:
    def __init__(self, url=CDP_URL, timeout=5):
        self.ws = websocket.create_connection(url, timeout=timeout,
                                              suppress_origin=True)
        self._id = 0
        self.events = []

    def call(self, method, params=None, session_id=None, timeout=None):
        self._id += 1
        msg = {"id": self._id, "method": method, "params": params or {}}
        if session_id:
            msg["sessionId"] = session_id
        self.ws.send(json.dumps(msg))
        self.ws.settimeout(timeout or 5)
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == self._id:
                return m
            self.events.append(m)

    def eval(self, expr, session_id, timeout=5):
        r = self.call("Runtime.evaluate",
                      {"expression": expr, "returnByValue": True,
                       "awaitPromise": True},
                      session_id=session_id, timeout=timeout)
        try:
            return r["result"]["result"].get("value")
        except (KeyError, TypeError):
            return r


def main():
    cdp = Cdp()
    targets = cdp.call("Target.getTargets")["result"]["targetInfos"]
    interesting = [t for t in targets
                   if t["type"] in ("worker", "page", "webview")]
    print(f"{len(targets)} 个 target，逐个探测（每个最多 3 秒）…")
    for i, t in enumerate(interesting):
        label = f"[{i}] {t['type']} {t['url'][:55]!r}"
        try:
            r = cdp.call("Target.attachToTarget",
                         {"targetId": t["targetId"], "flatten": True},
                         timeout=3)
            sid = r.get("result", {}).get("sessionId")
            if not sid:
                print(f"{label} attach失败: {json.dumps(r)[:100]}")
                continue
            val = cdp.eval(
                "typeof wx + '|' + typeof getCurrentPages + '|'"
                + f"location.href.slice(0,60)", sid, timeout=3)
            print(f"{label} -> {val}")
        except Exception as e:
            print(f"{label} -> 超时/失败({type(e).__name__})")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()

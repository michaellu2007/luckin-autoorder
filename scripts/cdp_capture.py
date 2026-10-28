"""通过 CDP 记录小程序网络请求（配合 WMPFDebugger，替代 mitmproxy 抓包）。

前置条件：
1. 微信里已打开瑞幸小程序（WeChatAppEx.exe 在跑）
2. WMPFDebugger 已启动并完成 hook：npx tsx src/index.ts --auto-detect
   （在 WMPFDebugger 目录下跑，默认调试端口 62000）

用法：python scripts/cdp_capture.py
     操作完小程序后 Ctrl+C 结束，然后 python main.py --parse-capture
产出：logs/capture.jsonl（格式与 mitmproxy addon 相同，--parse-capture 直接可用）
"""

import base64
import datetime as dt
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

import websocket

OUT = Path(__file__).resolve().parent.parent / "logs" / "capture.jsonl"
CDP_URL = "ws://127.0.0.1:62000"
HOST_KEYWORDS = ("lkcoffee", "luckincoffee")
MAX_BODY = 20000

pending = {}        # requestId -> entry 草稿
awaiting_body = {}  # CDP msg id -> requestId
_msg_id = 100


def next_id() -> int:
    global _msg_id
    _msg_id += 1
    return _msg_id


def flush(entry: dict):
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"[已记录] {entry['method']} {urlsplit(entry['url']).path} -> {entry['status']}")


def request_body(ws, rid: str):
    awaiting_body[next_id()] = rid
    ws.send(json.dumps({"id": _msg_id, "method": "Network.getResponseBody",
                        "params": {"requestId": rid}}))


def handle_message(ws, raw: str):
    msg = json.loads(raw)
    if "id" in msg:  # getResponseBody 的响应
        rid = awaiting_body.pop(msg.get("id"), None)
        if rid is None:
            return
        entry = pending.pop(rid, None)
        if entry is None:
            return
        result = msg.get("result") or {}
        body = result.get("body") or ""
        if result.get("base64Encoded"):
            try:
                body = base64.b64decode(body).decode("utf-8", errors="replace")
            except Exception:
                body = ""
        entry["resp_body"] = body[:MAX_BODY]
        flush(entry)
        return

    method, params = msg.get("method"), msg.get("params") or {}
    rid = params.get("requestId", "")
    if method == "Network.requestWillBeSent":
        url = params.get("request", {}).get("url", "")
        host = urlsplit(url).netloc
        if any(k in host for k in HOST_KEYWORDS):
            req = params["request"]
            pending[rid] = {
                "ts": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "method": req.get("method", ""),
                "url": url,
                "status": None,
                "req_headers": req.get("headers", {}),
                "req_body": (req.get("postData") or "")[:MAX_BODY],
                "resp_body": "",
            }
    elif method == "Network.responseReceived":
        entry = pending.get(rid)
        if entry is not None:
            entry["status"] = params.get("response", {}).get("status")
    elif method == "Network.loadingFinished":
        entry = pending.get(rid)
        if entry is not None and entry.get("status") is not None:
            request_body(ws, rid)
    elif method == "Network.loadingFailed":
        entry = pending.pop(rid, None)
        if entry is not None:
            entry["status"] = "failed"
            flush(entry)


def main():
    OUT.parent.mkdir(exist_ok=True)
    print(f"连接 CDP：{CDP_URL}")
    ws = websocket.create_connection(CDP_URL, timeout=5,
                                     suppress_origin=True)
    ws.send(json.dumps({"id": next_id(), "method": "Network.enable"}))
    print("已启用网络监听。现在去小程序里操作（菜单/优惠券/我的订单/确认订单）。")
    print("操作完成后按 Ctrl+C 结束，再运行 python main.py --parse-capture")
    try:
        while True:
            try:
                raw = ws.recv()
                if raw:
                    handle_message(ws, raw.decode() if isinstance(raw, bytes) else raw)
            except websocket.WebSocketTimeoutException:
                continue
    except KeyboardInterrupt:
        print(f"\n结束。共捕获 {len(pending)} 条未完成 + 已写入 {OUT}")
    finally:
        ws.close()


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()

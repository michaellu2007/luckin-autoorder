"""mitmproxy addon：把瑞幸域名的请求/响应追加记录到 logs/capture.jsonl。

由 `python main.py --capture` 以 mitmdump -s 本文件 方式启动，勿直接运行。
"""

import json
import os
import time

HOST_KEYWORDS = ("lkcoffee", "luckincoffee")
KEEP_REQ_HEADERS = ("authorization", "userid", "user_id", "content-type",
                    "channel", "cookie", "token")
MAX_BODY = 20000

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "logs", "capture.jsonl")
os.makedirs(os.path.dirname(OUT), exist_ok=True)


def _body_str(msg):
    try:
        return (msg.get_text() or "")[:MAX_BODY]
    except Exception:
        return ""


class Recorder:
    def response(self, flow):
        host = flow.request.pretty_host
        if not any(k in host for k in HOST_KEYWORDS):
            return
        entry = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "method": flow.request.method,
            "url": flow.request.pretty_url,
            "status": flow.response.status_code,
            "req_headers": {k: v for k, v in flow.request.headers.items()
                            if k.lower() in KEEP_REQ_HEADERS},
            "req_body": _body_str(flow.request),
            "resp_body": _body_str(flow.response),
        }
        with open(OUT, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


addons = [Recorder()]

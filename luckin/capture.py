"""抓包结果解析：从 logs/capture.jsonl 提取 token / 接口路径 / 门店 ID。

运行：python main.py --parse-capture
（抓包本体用 `python main.py --capture` 启动，addon 在 scripts/capture_addon.py）
产出：
- token.yaml          登录凭证（脚本运行用）
- endpoints.yaml      接口路径草稿，加载后覆盖 api.py 里的默认值
- logs/capture_report.md   全部请求清单和报文样本，用来对齐字段
"""

import datetime as dt
import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from . import config

HOST_KEYWORDS = ("lkcoffee", "luckincoffee")

# 路径里的关键词 → 接口用途（用于生成 endpoints.yaml 草稿；值 None 表示仅记录）
ENDPOINT_HINTS = {
    "menu": "menu", "product": "menu", "sku": "menu", "goods": "menu",
    "coupon": "coupons", "ticket": "coupons",
    "cart": "cart_preview", "preview": "cart_preview",
    "price": "cart_preview", "confirm": "cart_preview",
    "create": "order_create", "submit": "order_create",
    "pay": "order_pay", "cashier": "order_pay", "wallet": "order_pay",
}

STORE_ID_KEYS = ("storecode", "storeid", "shopid", "storeno")
UID_KEYS = ("userid", "customerid", "accountid")
MAX_REPORT_BODY = 1200


def parse(jsonl_path: Path = None):
    log = config.get_logger()
    jsonl_path = Path(jsonl_path) if jsonl_path else (config.LOG_DIR / "capture.jsonl")
    if not jsonl_path.exists():
        raise FileNotFoundError(
            f"找不到 {jsonl_path}\n先抓包：python main.py --capture（见 capture_token.md）")
    entries = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    if not entries:
        raise RuntimeError(
            "capture.jsonl 里没有有效记录：抓包时没抓到瑞幸域名的请求，"
            "大概率是微信没走代理或证书没装好，见 capture_token.md 的常见问题")

    ok_entries = [e for e in entries if e.get("status") == 200] or entries

    # 1. token / userId：请求头和报文里出现次数最多的值
    token_c, uid_c, store_c = Counter(), Counter(), Counter()

    def scan_keys(obj, counter, keys):
        if not isinstance(obj, dict):
            return
        for k, v in obj.items():
            if k.lower() in keys and v and not isinstance(v, (dict, list)):
                counter[str(v).strip()] += 1

    for e in ok_entries:
        for k, v in (e.get("req_headers") or {}).items():
            kl = k.lower()
            if kl in ("authorization", "token") and v:
                token_c[str(v).strip()] += 1
            if kl in UID_KEYS and v:
                uid_c[str(v).strip()] += 1
        for body_key in ("req_body", "resp_body"):
            try:
                scan_keys(json.loads(e.get(body_key) or "{}"), uid_c, UID_KEYS)
                scan_keys(json.loads(e.get(body_key) or "{}"), store_c, STORE_ID_KEYS)
            except (json.JSONDecodeError, AttributeError):
                pass

    token = token_c.most_common(1)[0][0] if token_c else ""
    user_id = uid_c.most_common(1)[0][0] if uid_c else ""

    # 2. 接口清单与 base 域名
    path_c, host_c = Counter(), Counter()
    for e in ok_entries:
        u = urlsplit(e["url"])
        host_c[u.netloc] += 1
        path_c[(u.netloc, u.path)] += 1
    capi = [(h, n) for h, n in host_c.items() if "capi" in h]
    base_host = (max(capi, key=lambda x: x[1])[0] if capi
                 else host_c.most_common(1)[0][0])

    # 3. endpoints.yaml 草稿
    draft = {"base": f"https://{base_host}"}
    assigned = set()
    for (host, path), _ in path_c.most_common():
        pl = path.lower()
        for kw, target in ENDPOINT_HINTS.items():
            if kw in pl and target and target not in assigned:
                draft[target] = path
                assigned.add(target)
                break
    with open(config.ROOT / "endpoints.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(draft, f, allow_unicode=True)

    # 4. token.yaml（保留已有字段）
    tok_path = config.ROOT / "token.yaml"
    tok = {}
    if tok_path.exists():
        tok = yaml.safe_load(tok_path.read_text(encoding="utf-8")) or {}
    if token:
        tok["token"] = token
    if user_id:
        tok["user_id"] = user_id
    tok["captured_at"] = dt.datetime.now().isoformat(timespec="seconds")
    config.save_token(tok)

    # 5. 报告：全部请求 + 报文样本
    lines = [
        "# 抓包解析报告",
        f"\n解析时间：{tok['captured_at']}　请求条数：{len(ok_entries)}（全部 {len(entries)}）",
        f"\n- token：`{token[:12]}…`" if token else "\n- ⚠️ 没有识别到 token",
        f"- userId：`{user_id}`" if user_id else "- 没识别到 userId（不一定是问题）",
        f"- base 域名：`https://{base_host}`",
    ]
    if store_c:
        lines.append("- 疑似门店 ID（选你常用的填进 config.yaml 的 store.id）：")
        lines += [f"  - `{v}`（出现 {n} 次）" for v, n in store_c.most_common(5)]
    lines.append("\n## 接口草稿（endpoints.yaml，需人工核对）\n")
    lines += [f"- `{k}` → `{v}`" for k, v in draft.items()]
    lines.append("\n## 抓到的全部接口（含报文样本，用来对齐 api.py 字段）\n")
    for (host, path), n in path_c.most_common():
        sample = next(e for e in ok_entries if urlsplit(e["url"]).path == path)
        lines.append(f"### `{sample['method']} https://{host}{path}`　× {n}\n")
        lines.append(f"- 请求体：`{sample.get('req_body', '')[:MAX_REPORT_BODY]}`")
        lines.append(f"- 响应体：`{sample.get('resp_body', '')[:MAX_REPORT_BODY]}`\n")
    report = "\n".join(lines)
    with open(config.LOG_DIR / "capture_report.md", "w", encoding="utf-8") as f:
        f.write(report)

    log.info("解析完成：token=%s%s，识别接口草稿 %d 项，报告在 logs/capture_report.md",
             token[:8], "…" if token else "（⚠️ 未识别到！）", len(draft) - 1)
    log.info("下一步：把 capture_report.md 发给助手对齐 api.py 字段，"
             "并把报告里的门店 ID 填进 config.yaml")

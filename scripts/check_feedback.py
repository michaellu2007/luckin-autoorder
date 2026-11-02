"""读取学邮回复的评分反馈，更新 ratings.yaml。

用法：python scripts/check_feedback.py
逻辑：IMAP 登录 163 邮箱 → 找来自学邮的未读/新邮件 → 解析「饮品名 + 分数」
（只写分数默认评最近一杯）→ 更新 ratings.yaml → 记录已处理邮件号避免重复。
"""

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PROCESSED = ROOT / "logs" / "feedback_processed.json"


def load_processed():
    if PROCESSED.exists():
        try:
            return set(json.loads(PROCESSED.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()


def save_processed(ids):
    PROCESSED.write_text(json.dumps(sorted(ids), ensure_ascii=False), encoding="utf-8")


def main():
    import imaplib
    import email
    from email.header import decode_header

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    ec = (cfg.get("notify") or {}).get("email") or {}
    addr, code = ec.get("from_addr"), ec.get("auth_code")
    student = ec.get("to_addr")
    if not (addr and code and student):
        print("邮箱配置不完整")
        return 1

    from luckin import picker as legacy_picker

    processed = load_processed()
    mail = imaplib.IMAP4_SSL("imap.163.com", 993)
    mail.login(addr, code)
    mail.select("INBOX", readonly=True)
    typ, data = mail.search(None, f'(FROM "{student}")')
    ids = data[0].split()
    new_msgs = [i for i in ids if i.decode() not in processed]
    print(f"学邮来信 {len(ids)} 封，未处理 {len(new_msgs)} 封")

    ratings = legacy_picker.load_ratings()
    recorded = []
    for mid in new_msgs:
        typ, msg_data = mail.fetch(mid, "(RFC822)")
        msg = email.message_from_bytes(msg_data[0][1])
        # 标题解码
        subject = ""
        for part, enc in decode_header(msg.get("Subject", "")):
            subject += part if isinstance(part, str) else part.decode(enc or "gbk", "ignore")
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    payload = part.get_payload(decode=True) or b""
                    charset = part.get_content_charset() or "utf-8"
                    body += payload.decode(charset, "ignore")
        else:
            payload = msg.get_payload(decode=True) or b""
            body += payload.decode(msg.get_content_charset() or "utf-8", "ignore")
        text = subject + " " + body

        # 解析：饮品名（可选）+ 分数
        score = None
        m = re.search(r"([1-5])\s*分", text) or re.search(r"([1-5])(?=\s*分)|(?<=[\s，。!！])([1-5])(?![0-9分])", text)
        m2 = re.search(r"([1-5])\s*分", text)
        if m2:
            score = int(m2.group(1))
        else:
            m3 = re.search(r"(?:^|\s)([1-5])(?:\s|$|[，。!！])", text)
            score = int(m3.group(1)) if m3 else None

        # 饮品名：匹配候选清单/已知饮品关键词，否则用最近一杯
        known = ["生椰拿铁", "埃塞金烘", "澳瑞白", "瑰夏", "美式", "拿铁"]
        drink = next((k for k in known if k in text), None)
        if drink is None or score is None:
            print(f"  邮件 {mid.decode()}「{subject[:30]}」：未解析出评分（drink={drink}, score={score}），跳过")
            processed.add(mid.decode())
            continue

        # 映射到 ratings 里的确切键
        key = next((k for k in ratings if drink.replace(" ", "").lower() in k.replace(" ", "").lower()
                    or k.replace(" ", "").lower() in drink.replace(" ", "").lower()),
                   drink)
        ratings[key] = float(score)
        legacy_picker.save_rating(key, float(score)) if hasattr(legacy_picker, "save_rating") else None
        recorded.append(f"{key} = {score} 分（来自「{subject[:30]}」）")
        processed.add(mid.decode())

    if recorded:
        with open(ROOT / "ratings.yaml", "w", encoding="utf-8") as f:
            f.write("# 喝完给这杯打分（1~5，5=最爱）。python main.py --rate 饮品名 分数\n"
                    "# 分数越高越容易被选中；没打分的饮品按 3 分（中性）参与抽选。\n")
            import yaml as _yaml
            _yaml.safe_dump(ratings, f, allow_unicode=True, sort_keys=False)
        print("✅ 已记录反馈：")
        for r in recorded:
            print("  ", r)
    save_processed(processed)
    mail.logout()
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())

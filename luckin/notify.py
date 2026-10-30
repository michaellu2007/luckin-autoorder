"""微信推送：Server酱 / PushPlus 二选一，见 config.yaml 的 notify 段。"""

import requests

from . import config


def _send_email(title: str, content: str, cfg: dict) -> bool:
    """SMTP 邮件通知。config.yaml 的 notify.email 段：
      smtp_host: smtp.qq.com    smtp_port: 465 (SSL)
      from_addr: 你的邮箱@qq.com
      auth_code: SMTP 授权码（不是邮箱密码！）
      to_addr:   收件邮箱（默认同 from_addr）
    """
    import smtplib
    from email.mime.text import MIMEText
    from email.header import Header
    ec = cfg.get("notify", {}).get("email") or {}
    host, port = ec.get("smtp_host"), int(ec.get("smtp_port") or 465)
    addr, code = ec.get("from_addr"), ec.get("auth_code")
    to = ec.get("to_addr") or addr
    if not (host and addr and code):
        return False
    msg = MIMEText(content, "plain", "utf-8")
    msg["Subject"] = Header(title, "utf-8")
    msg["From"] = addr
    msg["To"] = to
    with smtplib.SMTP_SSL(host, port, timeout=15) as srv:
        srv.login(addr, code)
        srv.sendmail(addr, [to], msg.as_string())
    return True


def send(title: str, content: str, cfg: dict) -> bool:
    notify = cfg.get("notify") or {}
    channel = str(notify.get("channel") or "none").lower()
    log = config.get_logger()
    proxy = notify.get("proxy") or None
    proxies = {"http": proxy, "https": proxy} if proxy else None
    try:
        if channel == "serverchan":
            key = notify.get("serverchan_sendkey")
            if not key:
                log.warning("notify.serverchan_sendkey 未配置，仅记日志：%s", title)
                return False
            r = requests.post(f"https://sctapi.ftqq.com/{key}.send",
                              data={"title": title, "desp": content},
                              timeout=10, proxies=proxies)
            ok = r.ok and r.json().get("code") == 0
        elif channel == "pushplus":
            token = notify.get("pushplus_token")
            if not token:
                log.warning("notify.pushplus_token 未配置，仅记日志：%s", title)
                return False
            r = requests.post("https://www.pushplus.plus/send",
                              json={"token": token, "title": title,
                                    "content": content, "template": "markdown"},
                              timeout=10, proxies=proxies)
            ok = r.ok and r.json().get("code") == 200
        elif channel == "email":
            ok = _send_email(title, content, cfg)
            if not ok:
                log.warning("邮件未发送：notify.email 配置不完整（host/addr/auth_code）")
            log.info("邮件推送%s：%s", "成功" if ok else "失败", title)
            return ok
        else:
            log.info("通知渠道为 none，仅记日志：%s", title)
            return False
        log.info("推送%s：%s", "成功" if ok else "失败", title)
        return ok
    except Exception as e:  # 推送失败不能影响主流程
        log.error("推送异常：%s（%s）", title, e)
        return False

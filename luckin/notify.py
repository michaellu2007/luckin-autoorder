"""微信推送：Server酱 / PushPlus 二选一，见 config.yaml 的 notify 段。"""

import requests

from . import config


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
        else:
            log.info("通知渠道为 none，仅记日志：%s", title)
            return False
        log.info("推送%s：%s", "成功" if ok else "失败", title)
        return ok
    except Exception as e:  # 推送失败不能影响主流程
        log.error("推送异常：%s（%s）", title, e)
        return False

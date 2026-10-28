"""下单主流程：星期/截止检查 → 幂等锁 → 选品 → 下单 → 尝试余额支付 → 推送。"""

import datetime as dt
import json
import time

import requests

from . import api, config, notify, picker

WEEKDAY_MAP = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}

RETRY_ATTEMPTS = 3
RETRY_DELAY_SEC = 15


def _with_retry(fn, log):
    """网络类异常自动重试；业务错误不重试（避免重复下单）。"""
    for i in range(RETRY_ATTEMPTS):
        try:
            return fn()
        except api.TokenExpired:
            raise
        except requests.RequestException as e:
            log.warning("第 %d/%d 次网络请求失败：%s", i + 1, RETRY_ATTEMPTS, e)
            if i == RETRY_ATTEMPTS - 1:
                raise
            time.sleep(RETRY_DELAY_SEC)


def run(cfg: dict, dry_run=False, force=False) -> int:
    log = config.get_logger()
    schedule = cfg.get("schedule") or {}

    # 计划任务可能开机补跑，先确认今天确实是配置的下单日、且没过当天截止时间
    if not force:
        want = WEEKDAY_MAP.get(str(schedule.get("weekday", "tue")).lower()[:3], 1)
        if dt.date.today().weekday() != want:
            log.info("今天不是配置的下单日（%s），跳过；测试用 --force",
                     schedule.get("weekday"))
            return 0
        deadline = schedule.get("deadline")
        if deadline:
            try:
                h, m = map(int, str(deadline).split(":"))
            except ValueError:
                log.warning("schedule.deadline 格式不对（应为 HH:MM）：%r，忽略", deadline)
            else:
                if dt.datetime.now().time() > dt.time(h, m):
                    log.info("已过当天截止时间 %s，放弃本轮", deadline)
                    return 0

    # 幂等锁：当天已创建过订单就不再下（--force 可越过）
    lock = config.LOG_DIR / f"order_{dt.date.today():%Y-%m-%d}.json"
    if lock.exists() and not force:
        log.info("今天已处理过（存在 %s），不重复下单；强制重下用 --force", lock.name)
        return 0

    store = cfg.get("store") or {}
    store_id = store.get("id")
    candidates = cfg.get("drinks") or []
    if not store_id or not candidates:
        log.error("config.yaml 里还没填 store.id / drinks，先完成配置和抓包")
        return 1

    try:
        token_info = config.load_token()
    except (FileNotFoundError, ValueError) as e:
        log.error("%s", e)
        notify.send("瑞幸脚本：需要重新抓包", str(e), cfg)
        return 1

    client = api.LuckinClient(token_info, config.load_endpoints(),
                              (cfg.get("api") or {}).get("proxy"))
    captured = token_info.get("captured_at")
    if captured:
        try:
            age_days = (dt.datetime.now()
                        - dt.datetime.fromisoformat(str(captured))).days
            if age_days >= 21:
                log.warning("token 已抓包 %d 天，可能临近过期，建议抽空重抓一次", age_days)
        except ValueError:
            pass
    log.info("拉取菜单和优惠券…")
    try:
        menu_items = api.normalize_menu(
            _with_retry(lambda: client.get_menu(store_id), log))
        coupons = api.normalize_coupons(
            _with_retry(lambda: client.get_coupons(), log))
    except api.TokenExpired as e:
        log.error("%s", e)
        notify.send("瑞幸脚本：token 过期", "请按 capture_token.md 重新抓包一次", cfg)
        return 1
    except Exception as e:
        log.exception("拉取菜单/优惠券失败：%s", e)
        notify.send("瑞幸脚本：拉取菜单失败", f"{e}\n详见 logs/run.log", cfg)
        return 1

    use_coupon = (cfg.get("order") or {}).get("use_coupon", True)
    order_cfg = cfg.get("order") or {}
    ratings = picker.load_ratings()
    choice, notes = picker.pick(
        candidates, menu_items, coupons if use_coupon else [],
        ratings=ratings,
        selection=order_cfg.get("selection", "cheap"),
        tolerance=float(order_cfg.get("price_tolerance", 1.0)))
    for n in notes:
        log.info("%s", n)
    if choice is None:
        msg = "候选饮品在菜单里都不可买（没匹配到/售罄），本周没下单。"
        log.warning(msg)
        notify.send("瑞幸脚本：本周没下单", msg + "\n\n" +
                    "\n".join(f"- {n}" for n in notes), cfg)
        return 1

    summary = (f"{choice['name']}（{choice['spec']}）\n"
               f"原价 {choice['price']} 元、券后实付 {choice['payable']} 元"
               + (f"（用券：{choice['coupon_name']}）" if choice["coupon_id"] else ""))

    def rate_hint() -> str:
        return ("\n\n喝完给这杯打个分吧（影响以后抽选权重）：\n"
                f"python main.py --rate {choice['name'].split('（')[0]} 1-5的分数")

    if dry_run:
        log.info("[DRY-RUN] 会点这一杯：%s（未真实下单）", summary.replace("\n", " "))
        return 0

    log.info("下单：%s", summary.replace("\n", " "))
    try:
        order = _with_retry(
            lambda: client.create_order(store_id, choice, choice["coupon_id"]), log)
    except Exception as e:
        log.exception("创建订单失败：%s", e)
        notify.send("瑞幸脚本：下单失败", f"{summary}\n\n错误：{e}", cfg)
        return 1

    # 订单创建成功立刻写幂等锁，之后无论支付成败都不会重复下单
    # TODO: 订单号/取餐码字段以抓包报文为准（常见 orderNo / pickupCode）
    order_no = str(order.get("orderNo") or order.get("orderId") or "")
    pickup_code = str(order.get("pickupCode") or order.get("pickupNo") or "")
    lock.write_text(json.dumps(
        {"order_no": order_no, "choice": choice,
         "created_at": dt.datetime.now().isoformat(timespec="seconds")},
        ensure_ascii=False, indent=2), encoding="utf-8")

    paid = False
    try:
        client.pay_by_wallet(order_no)
        paid = True
    except (api.LuckinError, requests.RequestException) as e:
        log.warning("余额支付没走通（%s），订单已创建，等你手动付款", e)

    store_name = store.get("name") or store_id
    if paid:
        notify.send("瑞幸下单成功 ✅",
                    f"{summary}\n订单号：{order_no}\n取餐码：{pickup_code}\n"
                    f"门店：{store_name}" + rate_hint(), cfg)
    else:
        notify.send("瑞幸订单已创建，等你付款 👉",
                    f"{summary}\n订单号：{order_no}\n门店：{store_name}\n\n"
                    "打开瑞幸小程序「我的订单」完成支付即可（想全自动支付，"
                    "请保持咖啡钱包有余额，见 README）。" + rate_hint(), cfg)
    return 0

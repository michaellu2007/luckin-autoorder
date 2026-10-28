"""瑞幸小程序私有接口封装。

所有接口路径和报文字段都以你账号的真实抓包为准：
- DEFAULT_ENDPOINTS 是按公开资料推测的默认值，未经真实验证（标 UNVERIFIED）
- 跑完 `python main.py --parse-capture` 后会生成 endpoints.yaml，加载后覆盖默认值
- 调用报 404 或业务码对不上时，把 logs/capture_report.md 里对应的请求报文
  发给助手对齐 api.py 的字段
"""

import requests


class LuckinError(Exception):
    """瑞幸接口业务错误。"""


class TokenExpired(LuckinError):
    """登录 token 过期/失效，需要重新抓包。"""


class CaptureNeeded(LuckinError):
    """缺少抓包解析出的接口路径，无法继续。"""


# UNVERIFIED：未经真实抓包验证，endpoints.yaml 存在时会被覆盖
DEFAULT_ENDPOINTS = {
    "base": "https://capi.lkcoffee.com",
    "store_detail": "/resource/m/sys/c/m/store/detail",
    "menu": "/resource/m/sys/c/m/menu/list",
    "coupons": "/resource/m/sys/c/m/coupon/list",
    "cart_preview": "/resource/m/sys/c/m/cart/preview",
    "order_create": "/resource/m/sys/c/m/order/createV4",
    "order_pay": "/resource/m/sys/c/m/order/pay",
}

# 成功业务码的真实取值以抓包为准，先按常见的 0/200 处理
SUCCESS_CODES = (0, "0", 200, "200")

TOKEN_EXPIRED_HINTS = ("401", "403", "登录", "login", "token")


class LuckinClient:
    def __init__(self, token_info: dict, endpoints: dict = None, proxy: str = ""):
        self.token = token_info["token"]
        self.user_id = token_info.get("user_id", "")
        eps = dict(DEFAULT_ENDPOINTS)
        if endpoints:
            eps.update({k: v for k, v in endpoints.items() if v})
        self.endpoints = eps
        self.session = requests.Session()
        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}
        self.session.headers.update({
            "Content-Type": "application/json",
            "Authorization": self.token,
            # UNVERIFIED：以下头字段以抓包报文为准，缺了可能被服务端拒
            "userId": str(self.user_id),
            "channel": "wxmp",
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "MicroMessenger/8.0.x miniProgram"),
        })

    def _call(self, name: str, payload: dict) -> dict:
        path = self.endpoints.get(name)
        if not path:
            raise CaptureNeeded(
                f"接口 {name} 还没有路径，先抓包并解析：python main.py --parse-capture"
            )
        url = self.endpoints["base"].rstrip("/") + path
        resp = self.session.post(url, json=payload, timeout=15)
        if resp.status_code in (401, 403):
            raise TokenExpired(
                f"HTTP {resp.status_code}：token 已过期，请按 capture_token.md 重新抓包"
            )
        if resp.status_code != 200:
            raise LuckinError(f"HTTP {resp.status_code} {url}: {resp.text[:200]}")
        try:
            data = resp.json()
        except ValueError:
            raise LuckinError(f"响应不是 JSON：{resp.text[:200]}")
        code = data.get("code", data.get("status"))
        msg = data.get("msg") or data.get("message") or ""
        if code not in SUCCESS_CODES:
            if any(h in str(code) for h in TOKEN_EXPIRED_HINTS):
                raise TokenExpired(f"业务码 {code} 表示登录失效，请重新抓包：{msg}")
            raise LuckinError(f"业务错误 code={code} msg={msg} url={path}")
        return data

    # ---- 业务方法（payload 字段以抓包报文为准，TODO 处待对齐）----

    def get_menu(self, store_id: str) -> dict:
        """门店菜单：饮品、规格、价格、售罄状态。"""
        return self._call("menu", {"storeCode": store_id})  # TODO: 字段抓包后核对

    def get_coupons(self) -> dict:
        """可用优惠券列表。"""
        return self._call(  # TODO: 字段抓包后核对
            "coupons", {"userId": self.user_id, "useStatus": 0}
        )

    def create_order(self, store_id: str, sku: dict, coupon_id: str = "") -> dict:
        """创建订单，返回订单号等信息。"""
        payload = {  # TODO: 字段以抓包报文为准
            "storeCode": store_id,
            "itemId": sku.get("item_id"),
            "skuId": sku.get("sku_id"),
            "count": 1,
            "couponId": coupon_id or "",
            "pickupType": 1,  # 自提
        }
        return self._call("order_create", payload)

    def pay_by_wallet(self, order_no: str) -> dict:
        """咖啡钱包余额支付。走不通会抛 LuckinError，由上层降级为手动付款。"""
        # TODO: 真实支付方式字段待抓包确认（也可能需要单独的收银台接口）
        return self._call("order_pay", {"orderNo": order_no, "payType": "wallet"})


def _to_float(v) -> float:
    try:
        return round(float(str(v).replace("¥", "").strip()), 2)
    except (TypeError, ValueError):
        return 0.0


def normalize_menu(raw) -> list:
    """把菜单报文归一成 picker 需要的结构，每个规格一条。

    TODO: 字段路径以抓包为准，现在的取法是按常见结构的猜测；
    解析 capture_report.md 后对齐。
    """
    if isinstance(raw, dict):
        body = raw.get("data", raw)
        if isinstance(body, dict):
            for key in ("productList", "products", "items", "list"):
                if key in body:
                    raw = body[key]
                    break
    items = []
    if not isinstance(raw, list):
        return items
    for prod in raw:
        if not isinstance(prod, dict):
            continue
        name = prod.get("productName") or prod.get("name") or ""
        skus = prod.get("skuList") or prod.get("skus") or [prod]
        for sku in skus:
            if not isinstance(sku, dict):
                continue
            items.append({
                "name": name,
                "item_id": prod.get("productId") or prod.get("itemId") or "",
                "sku_id": sku.get("skuId") or sku.get("id") or "",
                "spec": sku.get("spec") or sku.get("skuName") or "",
                "price": _to_float(sku.get("price") or sku.get("salePrice")
                                   or prod.get("price") or 0),
                "sold_out": bool(sku.get("soldOut") or sku.get("stockOut")
                                 or sku.get("sold_out")),
            })
    return items


def normalize_coupons(raw) -> list:
    """归一化优惠券 → [{id, name, discount, min_price, products}]。TODO 以抓包为准。"""
    if isinstance(raw, dict):
        body = raw.get("data", raw)
        if isinstance(body, dict):
            for key in ("couponList", "coupons", "list", "items"):
                if key in body:
                    raw = body[key]
                    break
    out = []
    if not isinstance(raw, list):
        return out
    for c in raw:
        if not isinstance(c, dict):
            continue
        out.append({
            "id": c.get("couponId") or c.get("id") or "",
            "name": c.get("couponName") or c.get("name") or "",
            "discount": _to_float(c.get("discountAmount") or c.get("discount")
                                  or c.get("reducePrice") or 0),
            "min_price": _to_float(c.get("minPrice") or c.get("threshold")
                                   or c.get("minConsume") or 0),
            "products": c.get("productNames") or c.get("products") or [],
        })
    return out

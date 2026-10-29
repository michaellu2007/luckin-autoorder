"""瑞幸官方 MCP 客户端（https://open.lkcoffee.com）。

端点：https://gwmcp.lkcoffee.com/order/user/mcp（remote / streamablehttp）
认证：Authorization: Bearer <Token>，Token 从 open.lkcoffee.com 登录后复制。

官方 8 个工具：
  queryShopList            查附近门店（门店名/经纬度）
  searchProductForMcp      自然语言搜商品
  switchProduct            切换规格（冰热/糖度/浓度/杯型/小料）
  queryProductDetailInfo   商品详情
  previewOrder             订单预览（纯算价，不生成订单）
  createOrder              创建订单（返回支付链接/二维码）
  queryOrderDetailInfo     订单状态与取餐码
  cancelOrder              取消订单
"""

import json

import requests

MCP_URL = "https://gwmcp.lkcoffee.com/order/user/mcp"


class LuckinMcp:
    def __init__(self, token: str, proxy: str = ""):
        self.session = requests.Session()
        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        })
        self._id = 0
        self._initialized = False

    def _rpc(self, method: str, params: dict = None) -> dict:
        self._id += 1
        body = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            body["params"] = params
        r = self.session.post(MCP_URL, json=body, timeout=30)
        if r.status_code == 401:
            raise PermissionError("Token 无效或过期：重新到 open.lkcoffee.com 复制")
        r.raise_for_status()
        # streamablehttp 可能返回 SSE 格式
        text = r.text.strip()
        if text.startswith("event:") or "\ndata:" in text or text.startswith("data:"):
            for line in text.splitlines():
                if line.startswith("data:"):
                    return json.loads(line[4:].strip())
            raise RuntimeError(f"MCP 响应格式异常：{text[:200]}")
        return r.json()

    def _ensure_init(self):
        if self._initialized:
            return
        r = self._rpc("initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "luckin-autoorder", "version": "1.0"},
        })
        self.session.headers.update(
            {"Mcp-Session-Id": r.get("result", {}).get("sessionId", "")})
        self._rpc("notifications/initialized")
        self._initialized = True

    def list_tools(self) -> list:
        self._ensure_init()
        r = self._rpc("tools/list")
        return [(t["name"], t.get("description", "")) for t in r["result"]["tools"]]

    def call(self, tool: str, arguments: dict) -> dict:
        """调用官方工具，返回解析后的 content（JSON 优先，纯文本兜底）。"""
        self._ensure_init()
        r = self._rpc("tools/call", {"name": tool, "arguments": arguments})
        if "error" in r:
            raise RuntimeError(f"MCP 错误: {r['error']}")
        contents = r.get("result", {}).get("content") or []
        texts = [c.get("text", "") for c in contents if c.get("type") == "text"]
        raw = "\n".join(texts)
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return {"raw": raw}

    # ---- 业务封装 ----

    def query_shop_list(self, **kw):
        return self.call("queryShopList", kw)

    def search_product(self, keyword: str, **kw):
        return self.call("searchProductForMcp", {"keyword": keyword, **kw})

    def product_detail(self, **kw):
        return self.call("queryProductDetailInfo", kw)

    def switch_product(self, **kw):
        return self.call("switchProduct", kw)

    def preview_order(self, **kw):
        return self.call("previewOrder", kw)

    def create_order(self, **kw):
        return self.call("createOrder", kw)

    def order_detail(self, **kw):
        return self.call("queryOrderDetailInfo", kw)

    def cancel_order(self, **kw):
        return self.call("cancelOrder", kw)

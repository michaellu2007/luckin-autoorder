"""官方 MCP 下单：精萃澳瑞白（大杯/热/意式拼配/默认浓度/不另外加糖/鲜牛奶）。

流程：previewOrder（拿自动匹配的券和实付价）→ createOrder → 保存支付链接到
logs/mcp_order_result.json。支付由本人完成（打开支付链接或小程序订单页付款）；
不付款订单会自动取消。
"""

import json
import pathlib
import sys
import time

from luckin.mcp_client import LuckinMcp

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEPT = 345726          # 复旦叶耀珍楼超市店 (No.7121)
PRODUCT = 4807         # 精萃澳瑞白
SKU = "SP3227-01122"   # 大杯/热/意式拼配/默认浓度/不另外加糖/鲜牛奶
LON, LAT = 121.5035, 31.2989


def main():
    import yaml
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    mcp = LuckinMcp(cfg["mcp_token"], proxy=(cfg.get("api") or {}).get("proxy") or "")

    print(f"[{time.strftime('%H:%M:%S')}] previewOrder…", flush=True)
    pv = mcp.preview_order(deptId=DEPT,
                           productList=[{"productId": PRODUCT, "skuCode": SKU, "amount": 1}])
    if pv.get("code") != 0:
        print("预览失败:", json.dumps(pv, ensure_ascii=False)[:300])
        return 1
    data = pv["data"]
    coupons = data.get("couponCodeList") or []
    price = data.get("discountPrice")
    print(f"实付 {price} 元（自动用券 {len(coupons)} 张）", flush=True)

    print("createOrder…", flush=True)
    r = mcp.create_order(deptId=DEPT,
                         productList=[{"productId": PRODUCT, "skuCode": SKU, "amount": 1}],
                         longitude=LON, latitude=LAT, couponCodeList=coupons)
    out = ROOT / "logs" / "mcp_order_result.json"
    out.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(r, ensure_ascii=False)[:800], flush=True)

    if r.get("code") == 0:
        print("\n✅ 订单已创建。支付链接/二维码见 logs/mcp_order_result.json，付款后凭取餐码取餐。")
        # 有推送 key 就推
        try:
            from luckin.notify import send
            send("瑞幸澳白已下单（待支付）",
                 f"实付 {price} 元，支付链接见 logs/mcp_order_result.json；"
                 "或直接在瑞幸小程序「我的订单」里付款。", cfg)
        except Exception:
            pass
        return 0
    print("\n下单未成功（如门店未营业会自动失败，无扣款）。")
    return 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())

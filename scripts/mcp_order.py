"""官方 MCP 自动下单：价格决策 + 爱好加权，一条命令完成。

  python scripts/mcp_order.py --dry    只出决策报告（查价、选品，不下单）
  python scripts/mcp_order.py          真实下单（价格规则通过才买）
"""

import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from luckin import picker as legacy_picker
from luckin import picker_mcp
from luckin.mcp_client import LuckinMcp


def main():
    import yaml
    dry = "--dry" in sys.argv
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    store = cfg.get("store") or {}
    dept_id = int(store.get("id") or 345726)
    loc = cfg.get("location") or {}
    mcp = LuckinMcp(cfg["mcp_token"], proxy=(cfg.get("api") or {}).get("proxy") or "")
    ratings = legacy_picker.load_ratings()

    print(f"[{time.strftime('%H:%M:%S')}] 门店 {dept_id}，开始选品决策…", flush=True)
    choice, notes = picker_mcp.decide(mcp, dept_id, cfg, ratings)
    for n in notes:
        print("  ·", n, flush=True)

    if choice is None:
        print("\n结论：这期没有值得买的，下周再战 ☕")
        return 0

    print(f"\n>>> 决策：{choice['name']} ¥{choice['price']}"
          f"（原价 {choice['init']}，{choice['source']}）", flush=True)
    if dry:
        print("[DRY] 不下单。去掉 --dry 执行真实下单。")
        return 0

    pv = mcp.preview_order(deptId=dept_id,
                           productList=[{"productId": choice["productId"],
                                         "skuCode": choice["skuCode"], "amount": 1}])
    if pv.get("code") != 0:
        print("预览失败:", json.dumps(pv, ensure_ascii=False)[:200])
        return 1
    coupons = pv["data"].get("couponCodeList") or []
    final_price = pv["data"].get("discountPrice")
    print(f"previewOrder 通过：实付 {final_price} 元，券 {len(coupons)} 张", flush=True)

    r = mcp.create_order(deptId=dept_id,
                         productList=[{"productId": choice["productId"],
                                       "skuCode": choice["skuCode"], "amount": 1}],
                         longitude=loc.get("longitude"), latitude=loc.get("latitude"),
                         couponCodeList=coupons)
    out = ROOT / "logs" / "mcp_order_result.json"
    out.write_text(json.dumps({"choice": choice, "final_price": final_price,
                               "result": r}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(r, ensure_ascii=False)[:600], flush=True)
    if r.get("code") == 0:
        print("\n✅ 下单成功。到瑞幸小程序「我的订单」付款（免密/钱包），取餐码见订单详情。")
        try:
            from luckin.notify import send
            send(f"瑞幸下单成功：{choice['name']} ¥{final_price}",
                 "请到小程序完成支付并查取餐码。", cfg)
        except Exception:
            pass
        return 0
    print("\n下单未成功（打烊/风控等会原样返回，无扣款）。")
    return 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())

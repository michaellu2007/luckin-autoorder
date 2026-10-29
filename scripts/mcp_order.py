"""官方 MCP 自动下单：价格决策 + 爱好加权，一条命令完成。

  python scripts/mcp_order.py --dry    只出决策报告（查价、选品，不下单）
  python scripts/mcp_order.py          真实下单（价格规则通过才买）
"""

import datetime
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from luckin import picker as legacy_picker
from luckin import picker_mcp
from luckin.mcp_client import LuckinMcp


def compute_pay_deadline(class_time: str, walk_min: int, make_min: int):
    """付款截止 = 上课 - 路程 - 制作：咖啡做好拿着走到教室刚好上课。"""
    now = datetime.datetime.now()
    h, m = map(int, class_time.split(":"))
    cls = now.replace(hour=h, minute=m, second=0, microsecond=0)
    return now, cls - datetime.timedelta(minutes=walk_min + make_min)


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

    # 时机计算：拿到咖啡走到教室刚好上课
    sched = cfg.get("schedule") or {}
    class_time = str(sched.get("class_time", "09:55"))
    walk_min = int(sched.get("walk_minutes", 6))
    make_min = int(sched.get("make_minutes", 12))
    now, pay_deadline = compute_pay_deadline(class_time, walk_min, make_min)
    if now < pay_deadline - datetime.timedelta(minutes=1):
        wait_s = int((pay_deadline - now).total_seconds())
        print(f"上课 {class_time}；最佳下单时刻 {pay_deadline:%H:%M}（付款后约 {make_min} 分钟"
              f"做好，留 {walk_min} 分钟走路）。等待 {wait_s} 秒…", flush=True)
        time.sleep(wait_s)
    print(f"[{time.strftime('%H:%M:%S')}] 到点，下单（请立即付款）", flush=True)

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
                 f"现在付款！约 {make_min} 分钟做好，留 {walk_min} 分钟走路，掐点取餐上课。", cfg)
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

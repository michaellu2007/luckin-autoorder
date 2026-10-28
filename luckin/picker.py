"""从候选饮品里选一杯。

- selection=cheap：券后实付最低，并列随机
- selection=balanced：先按券后价筛出「便宜档」（最低实付 + price_tolerance 元以内），
  再在档内按你的评分加权随机（ratings.yaml，未打分按中性分 3）

 ratings.yaml 读写也在这里：--rate 命令和手动编辑都落到这个文件。
"""

import random

import yaml

from . import config

RATINGS_FILE = config.ROOT / "ratings.yaml"
DEFAULT_SCORE = 3.0  # 没打过分的中性分


def load_ratings() -> dict:
    if not RATINGS_FILE.exists():
        return {}
    with open(RATINGS_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {str(k): float(v) for k, v in data.items() if v}


def save_rating(name: str, score: float):
    ratings = load_ratings()
    ratings[name] = score
    with open(RATINGS_FILE, "w", encoding="utf-8") as f:
        f.write("# 喝完给这杯打分（1~5，5=最爱）。python main.py --rate 饮品名 分数\n"
                "# 分数越高越容易被选中；没打分的饮品按 3 分（中性）参与抽选。\n")
        yaml.safe_dump(ratings, f, allow_unicode=True, sort_keys=False)


def _norm(s) -> str:
    return str(s).replace(" ", "").lower()


def _score_for(name, ratings: dict) -> float:
    """评分表里的键和菜单名互相包含即视为同款，取最高分。"""
    n = _norm(name)
    scores = [v for k, v in ratings.items()
              if (kn := _norm(k)) and (kn in n or n in kn)]
    return max(scores) if scores else DEFAULT_SCORE


def _coupon_ok(coupon, product_name) -> bool:
    prods = coupon.get("products") or []
    if not prods:
        return True
    return any(_norm(p) in _norm(product_name) or _norm(product_name) in _norm(p)
               for p in prods)


def _best_coupon(price, coupons, product_name):
    usable = [c for c in coupons
              if c.get("discount", 0) > 0
              and price >= c.get("min_price", 0)
              and _coupon_ok(c, product_name)]
    return max(usable, key=lambda c: c["discount"]) if usable else None


def pick(candidates, menu_items, coupons, ratings=None,
         selection="cheap", tolerance=1.0):
    """返回 (choice, notes)。候选全部不可买时 choice 为 None。"""
    ratings = ratings or {}
    notes, options = [], []
    for cand in candidates:
        matched = [m for m in menu_items if _norm(cand) in _norm(m["name"])]
        if not matched:
            notes.append(f"「{cand}」在菜单里没有匹配到")
            continue
        available = [m for m in matched if not m["sold_out"]]
        if not available:
            notes.append(f"「{cand}」匹配到 {len(matched)} 个规格但都售罄")
            continue
        for m in available:
            coupon = _best_coupon(m["price"], coupons, m["name"])
            payable = round(m["price"] - (coupon["discount"] if coupon else 0), 2)
            options.append({
                "name": m["name"],
                "spec": m["spec"],
                "item_id": m["item_id"],
                "sku_id": m["sku_id"],
                "price": m["price"],
                "coupon_id": coupon["id"] if coupon else "",
                "coupon_name": coupon["name"] if coupon else "",
                "payable": payable,
            })
    if not options:
        return None, notes

    cheapest = min(o["payable"] for o in options)
    if selection == "balanced":
        pool = [o for o in options if o["payable"] <= cheapest + tolerance]
        for o in pool:
            o["rating"] = _score_for(o["name"], ratings)
        choice = random.choices(pool, weights=[o["rating"] for o in pool], k=1)[0]
        notes.append(
            f"共 {len(options)} 个可买规格；实付 {cheapest}~{cheapest + tolerance} 元"
            f"的 {len(pool)} 个进入抽选，按评分加权随机"
            f"（选中 {choice['name']}，{choice['rating']} 分）")
    else:
        tied = [o for o in options if o["payable"] == cheapest]
        choice = random.choice(tied)
        notes.append(f"共 {len(options)} 个可买规格，最低实付 {cheapest} 元"
                     + (f"（{len(tied)} 个并列，随机取一）" if len(tied) > 1 else ""))
    return choice, notes

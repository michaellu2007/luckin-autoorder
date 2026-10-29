"""选品决策引擎 v2（官方 MCP 版）：爱好分析 + 价格判断。

价格规则（config.yaml 的 price_rules）：
  default_max     常规款上限：超过就放弃该款（如 11 元的澳白不买）
  deal_max        惊喜价：低于此价闭眼买，同价里评分高者优先
  new_product_max 一口价/新品尝试上限

决策顺序：
  1. 搜候选清单每款 → 拿优惠后预估价（estimatePrice）
  2. 搜一口价/新品 → 加入尝鲜池
  3. 过滤：超上限的淘汰
  4. 最低价者胜；同价（±0.2）按 ratings.yaml 评分加权随机
"""

import random

from .mcp_client import LuckinMcp

ROOT = None  # 延迟解析，避免循环导入


def _root():
    global ROOT
    if ROOT is None:
        from . import config
        ROOT = config.ROOT
    return ROOT


def history_profile() -> dict:
    """从订单历史算口味画像：{家族: 购买次数}。文件不存在返回空。"""
    import json
    root = _root()
    for f in ("logs/orders_full.json", "logs/orders_20261029.json"):
        path = root / f
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        flat = [o for grp in data for o in (grp if isinstance(grp, list) else [grp])]
        done = [o for o in flat if o.get("orderStatusCode") in (80, 92)]
        fam = {}
        for o in done:
            n = str(o.get("goodsName", ""))
            key = None
            if "埃塞" in n: key = "埃塞金烘系列"
            elif "瑰夏" in n: key = "瑰夏冷萃系列"
            elif "生椰" in n: key = "生椰拿铁"
            elif "美式" in n or "冷萃" in n: key = "美式冷萃类"
            else: key = "尝鲜新品"
            fam[key] = fam.get(key, 0) + 1
        return fam
    return {}


def _family(name: str) -> str:
    n = str(name)
    if "埃塞" in n: return "埃塞金烘系列"
    if "瑰夏" in n: return "瑰夏冷萃系列"
    if "生椰" in n: return "生椰拿铁"
    if "美式" in n or "冷萃" in n: return "美式冷萃类"
    return "尝鲜新品"


def _norm(s) -> str:
    return str(s).replace(" ", "").lower()


def _search_all(mcp: LuckinMcp, dept_id: int, query: str) -> list:
    r = mcp.search_product(query=query, deptId=dept_id)
    if not isinstance(r, dict) or r.get("code") != 0:
        return []
    items = r.get("data") or []
    return items if isinstance(items, list) else []


def _first_sku(item: dict) -> str:
    return item.get("skuCode") or ""


def decide(mcp: LuckinMcp, dept_id: int, cfg: dict, ratings: dict) -> tuple:
    """返回 (choice, notes)。无可买项时 choice 为 None。"""
    rules = cfg.get("price_rules") or {}
    default_max = float(rules.get("default_max", 10.9))
    deal_max = float(rules.get("deal_max", 9.0))
    new_max = float(rules.get("new_product_max", 12.9))
    drinks = cfg.get("drinks") or []

    notes = []
    pool = []  # {name, productId, skuCode, price, source}

    # 1. 常规候选
    for drink in drinks:
        items = _search_all(mcp, dept_id, drink)
        if not items:
            notes.append(f"「{drink}」门店没有匹配商品")
            continue
        # 同名去重取预估最低的 sku
        best = min(items, key=lambda x: float(x.get("estimatePrice", 999)))
        name = best.get("productName", drink)
        price = float(best.get("estimatePrice", 999))
        init = float(best.get("initialPrice", 0))
        if price > default_max:
            notes.append(f"「{name}」{price} 元 > 上限 {default_max}，放弃")
            continue
        tag = "惊喜价⚡" if price <= deal_max else "常规价"
        pool.append({"name": name, "productId": int(best.get("productId")),
                     "skuCode": _first_sku(best), "price": price,
                     "init": init, "source": f"候选清单·{tag}"})
        notes.append(f"「{name}」优惠后 {price} 元（原价 {init}）→ {tag}")

    # 2. 一口价/新品
    for kw in ("一口价", "新品"):
        items = _search_all(mcp, dept_id, kw)
        known = {p["productId"] for p in pool}
        for it in items:
            pid = int(it.get("productId", 0))
            if pid in known or pid == 0:
                continue
            name = it.get("productName", "")
            price = float(it.get("estimatePrice", 999))
            init = float(it.get("initialPrice", 0))
            if price > new_max:
                continue
            pool.append({"name": name, "productId": pid,
                         "skuCode": _first_sku(it), "price": price,
                         "init": init, "source": f"尝鲜·{kw}（原价 {init}）"})
            known.add(pid)
        if items:
            notes.append(f"「{kw}」搜索到 {len(items)} 个，入池 {max(0, len([p for p in pool if kw in p['source']]))} 个")

    if not pool:
        return None, notes, []

    # 3. 选品：最低价优先，同价（±0.2）按 评分×复购 加权随机；全部候选输出透明报告
    profile = history_profile()
    max_freq = max(profile.values()) if profile else 1
    cheapest = min(p["price"] for p in pool)
    near = [p for p in pool if p["price"] <= cheapest + 0.2]
    report = []
    for p in sorted(pool, key=lambda x: x["price"]):
        fam = _family(p["name"])
        freq = profile.get(fam, 0)
        rating = max(0.5, float(ratings.get(_norm_key(p["name"]), 3.0)))
        h_score = 1.0 + (freq / max_freq if max_freq else 0)
        weight = round(rating * h_score, 2)
        if p["price"] > cheapest + 0.2:
            verdict = f"贵 {(p['price'] - cheapest):.2f} 元，未选"
        elif len(near) > 1:
            verdict = "同价档参与加权抽选"
        else:
            verdict = "最低价，直接胜出"
        report.append({"name": p["name"], "price": p["price"], "init": p["init"],
                       "source": p["source"], "family": fam, "freq": freq,
                       "rating": rating, "weight": weight, "verdict": verdict,
                       "winner": p is near[0] or p in near})
    for r in report:
        r["winner"] = r["name"] == choice_name if (choice_name := None) else r["winner"]
    if len(near) == 1:
        choice = near[0]
    else:
        weights = []
        for p in near:
            r_score = max(0.5, float(ratings.get(_norm_key(p["name"]), 3.0)))
            freq = profile.get(_family(p["name"]), 0)
            weights.append(r_score * (1.0 + (freq / max_freq if max_freq else 0)))
        choice = random.choices(near, weights=weights, k=1)[0]
        names = "、".join(f"{p['name']}({p['price']})" for p in near)
        notes.append(f"同价档 {names}，按 评分×历史复购 加权随机（画像：{profile}）")
    for r in report:
        r["winner"] = r["name"] == choice["name"]
    return choice, notes, report


def _norm_key(name: str) -> str:
    for k in ("拿铁", "美式", "澳瑞白", "冷萃", "生椰"):
        if k in name:
            return k
    return _norm(name)

"""选品逻辑的单元测试：python -m unittest discover -s tests"""

import random
import unittest

from luckin import picker

MENU = [
    {"name": "生椰拿铁", "item_id": "p1", "sku_id": "s1", "spec": "标准/热",
     "price": 9.9, "sold_out": False},
    {"name": "埃塞俄比亚金烘拿铁", "item_id": "p2", "sku_id": "s2", "spec": "标准",
     "price": 10.5, "sold_out": False},
    {"name": "橙C美式", "item_id": "p3", "sku_id": "s3", "spec": "大杯",
     "price": 16.9, "sold_out": False},
    {"name": "厚乳拿铁", "item_id": "p4", "sku_id": "s4", "spec": "标准",
     "price": 13.9, "sold_out": True},
]

COUPONS = [{"id": "c1", "name": "4.9元券", "discount": 4.9,
            "min_price": 0, "products": []}]


class TestCheapMode(unittest.TestCase):
    def test_picks_lowest_payable(self):
        choice, _ = picker.pick(["生椰拿铁", "埃塞", "橙C美式"], MENU, COUPONS,
                                selection="cheap")
        self.assertEqual(choice["name"], "生椰拿铁")
        self.assertEqual(choice["payable"], 5.0)  # 9.9 - 4.9 券

    def test_coupon_applied(self):
        choice, _ = picker.pick(["橙C美式"], MENU, COUPONS, selection="cheap")
        self.assertEqual(choice["payable"], 12.0)  # 16.9 - 4.9
        self.assertEqual(choice["coupon_id"], "c1")

    def test_sold_out_skipped(self):
        choice, notes = picker.pick(["厚乳拿铁"], MENU, [], selection="cheap")
        self.assertIsNone(choice)
        self.assertTrue(any("售罄" in n for n in notes))

    def test_unknown_candidate_reported(self):
        choice, notes = picker.pick(["不存在的咖啡"], MENU, [], selection="cheap")
        self.assertIsNone(choice)
        self.assertTrue(any("没有匹配到" in n for n in notes))


class TestBalancedMode(unittest.TestCase):
    def test_respects_price_tolerance(self):
        random.seed(7)
        for _ in range(100):
            choice, _ = picker.pick(
                ["生椰拿铁", "埃塞", "橙C美式"], MENU, COUPONS,
                ratings={}, selection="balanced", tolerance=1.0)
            # 橙C 16.9 超出 9.9+1.0 容差，绝不该中
            self.assertIn(choice["name"], ("生椰拿铁", "埃塞俄比亚金烘拿铁"))

    def test_rating_weights_take_effect(self):
        random.seed(7)
        ratings = {"生椰拿铁": 5.0, "埃塞俄比亚金烘拿铁": 1.0}
        counts = {"生椰拿铁": 0, "埃塞俄比亚金烘拿铁": 0}
        for _ in range(500):
            choice, _ = picker.pick(["生椰拿铁", "埃塞"], MENU, [],
                                    ratings=ratings, selection="balanced",
                                    tolerance=1.0)
            counts[choice["name"]] += 1
        self.assertGreater(counts["生椰拿铁"], counts["埃塞俄比亚金烘拿铁"] * 3)

    def test_unrated_gets_neutral_score(self):
        # 全部没打分时按中性分均匀抽选，两杯都该有机会
        random.seed(3)
        names = set()
        for _ in range(100):
            choice, _ = picker.pick(["生椰拿铁", "埃塞"], MENU, [],
                                    ratings={}, selection="balanced",
                                    tolerance=1.0)
            names.add(choice["name"])
        self.assertEqual(names, {"生椰拿铁", "埃塞俄比亚金烘拿铁"})


if __name__ == "__main__":
    unittest.main()

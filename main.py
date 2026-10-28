"""瑞幸自动下单脚本入口。

用法：
  python main.py --run             真实下单（仅配置的下单日；测试加 --force）
  python main.py --dry-run         干跑：查菜单/算价/选品，不真实下单
  python main.py --test-notify     推一条测试消息验证微信推送
  python main.py --capture         启动抓包代理（见 capture_token.md）
  python main.py --parse-capture   解析 logs/capture.jsonl 产出 token/接口/报告
  python main.py --rate 生椰拿铁 5  给喝过的饮品打分（1~5，写入 ratings.yaml）
  python main.py --status          查看配置/凭证/计划任务状态
  --force                          跳过星期/截止时间/幂等锁检查
"""

import argparse
import shutil
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from luckin import config


def cmd_capture(port: int) -> int:
    mitmdump = shutil.which("mitmdump")
    if not mitmdump:
        print("没找到 mitmdump，先装抓包依赖：pip install -r requirements.txt")
        return 1
    addon = config.ROOT / "scripts" / "capture_addon.py"
    print(f"抓包代理启动在 127.0.0.1:{port}，记录写入 logs/capture.jsonl")
    print("按 capture_token.md 配好系统代理和证书后，打开微信里的瑞幸小程序操作。")
    print("操作完成后按 Ctrl+C 结束，再运行：python main.py --parse-capture")
    subprocess.call([mitmdump, "--listen-port", str(port), "-s", str(addon)])
    return 0


def cmd_status() -> int:
    import datetime as dt
    import subprocess

    import yaml

    from luckin import picker

    try:
        cfg = config.load_config()
    except FileNotFoundError as e:
        print(f"[配置问题] {e}")
        return 1

    sched = cfg.get("schedule") or {}
    print(f"计划      ：每周{sched.get('weekday', '?')} "
          f"{sched.get('time', '?')}（当天 {sched.get('deadline', '?')} 前可补跑）")
    store = cfg.get("store") or {}
    print(f"门店      ：{store.get('name') or '未填'}"
          f"（ID: {store.get('id') or '未填，待抓包'}）")
    print(f"候选饮品  ：{'、'.join(cfg.get('drinks') or []) or '未填'}")
    order_cfg = cfg.get("order") or {}
    print(f"选品模式  ：{order_cfg.get('selection', 'cheap')}"
          f"（便宜档容差 {order_cfg.get('price_tolerance', 1.0)} 元）")

    ratings = picker.load_ratings()
    print("评分      ：" + ("、".join(f"{k} {v:g} 分" for k, v in ratings.items())
                             or "还没有评分"))

    tok_path = config.ROOT / "token.yaml"
    if tok_path.exists():
        try:
            captured = (yaml.safe_load(tok_path.read_text(encoding="utf-8"))
                        or {}).get("captured_at", "")
            age = (dt.datetime.now()
                   - dt.datetime.fromisoformat(str(captured))).days
            hint = "（一般几周到几个月过期，建议 3 周以上就抽空重抓）" if age >= 21 else ""
            print(f"登录凭证  ：{age} 天前抓包 {hint}")
        except (ValueError, TypeError):
            print("登录凭证  ：token.yaml 存在但没有有效抓包时间")
    else:
        print("登录凭证  ：还没有（未抓包，见 capture_token.md）")

    locks = sorted(config.LOG_DIR.glob("order_*.json"))
    print(f"历史下单  ：{len(locks)} 条" +
          (f"，最近 {locks[-1].stem}" if locks else ""))

    # 中文 Windows 的 schtasks 输出是 GBK，按系统默认编码解码
    r = subprocess.run(["schtasks", "/query", "/tn", "LuckinAutoTuesday"],
                       capture_output=True, errors="replace")
    print("计划任务  ：" + ("已注册（LuckinAutoTuesday）" if r.returncode == 0
                           else "未注册（跑 scripts/register_task.ps1）"))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="每周二早上自动点一杯瑞幸")
    ap.add_argument("--run", action="store_true", help="真实下单")
    ap.add_argument("--dry-run", action="store_true", help="干跑：只选品不下单")
    ap.add_argument("--test-notify", action="store_true", help="测试微信推送")
    ap.add_argument("--capture", action="store_true", help="启动抓包代理（需 mitmproxy）")
    ap.add_argument("--parse-capture", action="store_true",
                    help="解析 logs/capture.jsonl，生成 token/endpoints/报告")
    ap.add_argument("--force", action="store_true", help="跳过星期/截止/幂等锁检查")
    ap.add_argument("--status", action="store_true", help="查看配置/凭证/计划任务状态")
    ap.add_argument("--rate", nargs=2, metavar=("饮品", "分数"),
                    help="给喝过的饮品打分 1~5，影响以后抽选权重，如：--rate 生椰拿铁 5")
    ap.add_argument("--port", type=int, default=18899, help="抓包代理端口，默认 18899")
    args = ap.parse_args()

    try:
        if args.status:
            return cmd_status()
        if args.rate:
            from luckin import picker
            name, score = args.rate[0].strip(), float(args.rate[1])
            if not 1 <= score <= 5:
                print("分数要在 1~5 之间")
                return 1
            picker.save_rating(name, score)
            print(f"已记录：{name} = {score} 分")
            print("当前评分表：", picker.load_ratings())
            return 0
        if args.capture:
            return cmd_capture(args.port)
        if args.parse_capture:
            from luckin import capture
            capture.parse()
            return 0
        if args.test_notify:
            cfg = config.load_config()
            from luckin import notify
            ok = notify.send("瑞幸脚本测试", "收到这条说明微信推送配置 OK ✅", cfg)
            print("推送" + ("成功" if ok else "未发送，原因看 logs/run.log"))
            return 0 if ok else 1
        if args.dry_run or args.run:
            cfg = config.load_config()
            from luckin import order
            return order.run(cfg, dry_run=args.dry_run, force=args.force)
    except FileNotFoundError as e:
        print(f"[配置问题] {e}")
        return 1
    except Exception as e:
        config.get_logger().exception("未预期的错误：%s", e)
        return 1

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

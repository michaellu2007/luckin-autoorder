# luckin-autoorder ☕

![CI](https://github.com/michaellu2007/luckin-autoorder/actions/workflows/ci.yml/badge.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Python](https://img.shields.io/badge/Python-3.9%2B-blue)

每周固定那天早上，自动帮你点好一杯瑞幸：从你心仪的饮品清单里选「券后实付最低」的一杯
（可选按你的个人评分加权随机），下单结果推送到微信，到店扫码取餐即可。

> 非官方工具。瑞幸没有开放下单 API，本项目通过抓包获取**你自己账号**的登录凭证，
> 调用瑞幸小程序接口实现自动化。请仅用于个人自用，理解并接受其中的风险（见文末）。

## 功能

- **定时下单**：Windows 计划任务每周固定时间自动执行，错过触发点（电脑当时关机）
  开机后当天内补跑，幂等锁保证绝不重复下单
- **智能选品**：自动套用最划算的优惠券，在心仪清单里选券后最低价；
  `balanced` 模式在「便宜档」（最低实付 + 容差元）内按个人评分加权随机——
  分越高越常喝到，没打分的新品也有机会
- **口味评分**：喝完 `python main.py --rate 生椰拿铁 5` 打个分，影响以后抽选权重
- **微信推送**：下单成功/需要付款/出错/token 过期，通过 Server酱 或 PushPlus 通知
- **支付策略**：优先咖啡钱包余额支付（全自动）；余额不足自动降级为
  「创建订单 + 推送提醒你点一下付款」

## 环境要求

- Windows（计划任务脚本基于 schtasks/PowerShell；核心代码理论上跨平台）
- Python 3.9+
- 一个能打开瑞幸小程序的电脑微信（仅抓包时需要）

## 快速开始

```bash
pip install -r requirements.txt
copy config.example.yaml config.yaml   # 填饮品清单、推送 key
```

然后按 [capture_token.md](capture_token.md) 做一次抓包（约 10 分钟），拿到你账号的
登录 token 和门店 ID。之后：

```bash
python main.py --test-notify       # 验证微信推送
python main.py --dry-run           # 干跑：查菜单、算价格、看选品结果，不花钱
python main.py --run --force       # 手动真实下一单，验证全流程
```

最后注册计划任务（PowerShell）：

```powershell
.\scripts\register_task.ps1        # 默认每周二 08:30，改 config.yaml 后重跑即可更新
```

## 日常使用

| 场景 | 命令/操作 |
|---|---|
| 改饮品清单 / 换时间 | 编辑 `config.yaml`（换时间需重跑 register_task.ps1） |
| 给喝过的饮品打分 | `python main.py --rate 饮品名 1~5` 或编辑 `ratings.yaml` |
| 立刻来一杯 | `python main.py --run --force` |
| token 过期提醒后重抓 | 照 [capture_token.md](capture_token.md) 再抓一次 |
| 看运行日志 / 历史订单 | `logs/run.log`、`logs/order_日期.json` |

## 隐私

所有个人信息（token、推送 key、门店、订单日志、口味评分）都在 `.gitignore` 排除
范围内，clone 后 fork/修改/上传都不会带出你的隐私。`config.yaml`、`ratings.yaml`
等请勿手动提交。

## 项目结构

```
luckin-auto/
├── main.py                  # 入口：--run / --dry-run / --rate / --status / --capture …
├── config.example.yaml      # 配置模板（复制为 config.yaml，隐私文件不入库）
├── capture_token.md         # 抓包教程（首次 & token 过期后照做）
├── luckin/
│   ├── api.py               # 瑞幸接口封装（路径以抓包解析出的 endpoints.yaml 为准）
│   ├── picker.py            # 选品：券后价便宜档内按评分加权随机
│   ├── order.py             # 下单主流程 + 支付降级 + 幂等锁
│   ├── capture.py           # 抓包记录解析（token / 门店 / 接口草稿）
│   ├── config.py            # 配置、凭证、日志
│   └── notify.py            # Server酱 / PushPlus 微信推送
├── scripts/
│   ├── capture_addon.py     # mitmproxy 记录插件
│   └── register_task.ps1    # 注册 Windows 计划任务（时间自动读 config.yaml）
└── tests/                   # 单元测试（CI 跑的就是这些）
```

## 常见问题

- **为什么不能全自动微信支付？** 微信支付必须本人确认，脚本无法代付。全自动支付
  依赖咖啡钱包余额或免密支付，否则自动降级为推送提醒你点一下付款。
- **token 多久失效一次？** 因人而异（一般几周到几个月）。失效时推送会提醒你，
  照 capture_token.md 重抓即可，证书装过一次后流程只需几分钟。
- **换了常去的门店怎么办？** 重新抓包一次，把解析报告里的新门店 ID 填进 config.yaml。
- **会不会重复下单？** 不会。当天存在订单锁文件就直接跳过；检查/取消见
  `logs/order_日期.json`。
- **电脑周二早上没开机怎么办？** 计划任务配置了开机补跑，当天截止时间（默认 14:00）
  前开机会自动补；过了就本周跳过，不会下午突兀来一杯。

## 开发

```bash
python -m unittest discover -s tests   # 单元测试（选品逻辑）
python main.py --dry-run               # 不花钱的全链路演练（需先抓包）
```

欢迎 Issue / PR。注意**不要**把 config.yaml、token.yaml、ratings.yaml、logs/
提交进来（.gitignore 已拦截，写代码时也请别绕过它）。

## 风险与免责

- 本项目调用瑞幸小程序私有接口，非官方用法，存在接口变动失效、账号被风控的
  小概率风险，请自行斟酌；由此造成的任何损失由使用者自己承担
- 请勿用于刷单、代下、转售等用途

## License

[MIT](LICENSE)

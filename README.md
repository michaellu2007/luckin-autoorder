# luckin-auto：每周二早上自动点一杯瑞幸

原理：抓包拿到你自己账号的登录 token，Python 直接调瑞幸小程序接口下单；
Windows 计划任务每周二 08:30 自动触发。从候选饮品里选「券后实付最低」的一杯
（并列随机），结果微信推送给你。

## 首次配置（约 15 分钟 + 一次抓包）

1. `pip install -r requirements.txt`
2. `copy config.example.yaml config.yaml`，填：候选饮品、推送 key
   （门店 ID 要等抓包后从报告里拿）
3. 按 `capture_token.md` 抓包一次 → `python main.py --parse-capture`
   → 把报告里的门店 ID 填进 config.yaml
4. `python main.py --test-notify` 验证微信推送
5. `python main.py --dry-run` 看选品结果（不花钱）
6. `python main.py --run --force` 手动真实下一单，验证全流程
7. PowerShell 运行 `scripts\register_task.ps1`，注册每周二 08:30 的计划任务

## 日常

- 全自动，无需操心；token 过期会微信推送提醒你重抓（照 capture_token.md 做）
- 改饮品清单：编辑 config.yaml 的 `drinks`
- 日志：`logs/run.log`；当日下单记录：`logs/order_日期.json`（也是幂等锁）
- 手动立刻来一杯：`python main.py --run --force`

## 全自动支付说明

微信支付无法被脚本代付。全自动支付的前提是：

- 瑞幸「咖啡钱包」里有余额（推荐，充值/攒券时顺手保持有余额），
  或账号开通了小额免密支付
- 两者都没有时脚本会自动降级：创建订单 + 微信推送提醒你点一下付款，不会白跑

## 风险提示

- 调用的是瑞幸小程序私有接口（非官方 API），严格说违反用户协议，
  有账号被风控的小概率风险，自行斟酌
- 瑞幸改版接口会导致脚本失效，需重新抓包对齐 api.py 字段

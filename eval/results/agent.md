# Eval 結果：agent（gpt-5-mini）

| 指標 | 分數 |
|---|---|
| 事件召回率 Event recall | 100% |
| 事件精確率 Event precision | 100% |
| 撞名排除率 Decoy rejection | 100% |
| 原因正確率 Cause accuracy | 100% |
| 情緒正確率 Sentiment accuracy | 89% |
| 證據精確率 Evidence precision | 100% |

## 逐事件結果

| 情境 | 埋設事件 | 日期 | 類型 | Agent 判斷 | 原因對 | 情緒對 | 證據 |
|---|---|---|---|---|---|---|---|
| coffee | coffee_ice | 2026-08-12 | 事件 | event | ✓ | ✓ | 2/2 |
| coffee | coffee_decoy_sunrise | 2026-08-27 | 撞名 | unrelated | — | — | — |
| coffee | coffee_collab | 2026-09-08 | 事件 | event | ✓ | ✓ | 2/2 |
| coffee | coffee_app | 2026-09-30 | 事件 | event | ✓ | ✓ | 2/2 |
| tea | tea_price | 2026-08-05 | 事件 | event | ✓ | ✗ | 3/3 |
| tea | tea_expired | 2026-09-16 | 事件 | event | ✓ | ✓ | 2/2 |
| tea | tea_taro | 2026-10-06 | 事件 | event | ✓ | ✓ | 2/2 |
| phone | phone_launch | 2026-08-07 | 事件 | event | ✓ | ✓ | 2/2 |
| phone | phone_decoy_leopard | 2026-08-20 | 撞名 | unrelated | — | — | — |
| phone | phone_green_line | 2026-09-01 | 事件 | event | ✓ | ✓ | 3/3 |
| phone | phone_repair | 2026-09-22 | 事件 | event | ✓ | ✓ | 2/2 |

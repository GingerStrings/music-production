# CSW 专用控制参考

参考 8 页版 CSW Manual。手册未标注脚本构建，请结合项目确认实际版本及所选 patch 可用的奏法。

## 默认控制

| 控制 | 本库含义 | 来源 |
| --- | --- | --- |
| CC1 | 长音动态；短音 selector 默认可用它选择类型 | pp.3、6–7 |
| CC11 | Config 图中的 Volume，可重映射 | p.7 图 |
| CC2 | Config 图标为 Vibrato On/Off；适用乐器和开关边界未在正文中充分定义 | p.7 图 |
| CC58 | 下列离散命令，可重映射 | pp.7–8 |

CC2 的截图标签只支持开关语义，不支持推断为连续深度，也不能据此给所有木管统一加入振音。

## 默认 CC58 命令

| 闭区间 | 动作 |
| --- | --- |
| 0–10 | Sustain |
| 11–15 | Repetitions |
| 16–20 | Staccatissimo |
| 21–25 | Staccato |
| 26–30 | Sfz |
| 46–50 | Trills |
| 51–55 | Flutter Tongue，长笛类限定 |
| 61–65 | Measured repetitions |
| 66–70 | Marcato，无 Repetition overlay |
| 71–75 | Marcato，有 Repetition overlay |
| 76–80 | Legato On |
| 81–85 | Legato Off |

来源：p.8。31–45、56–60、86–127 未列命令；保持未定义，不能填入其他库的拨弦、弱音或 Tremolo。

## 音符 keyswitch 自身的力度

核实数字键号后使用，实际 note-on 力度从 1 起。

| 开关 | 力度与动作 |
| --- | --- |
| Staccato | 1–32 Repetitions；33–64 Staccatissimo；65–96 Staccato；97–127 Sfz |
| Marcato | 1–64 Repetition overlay off；65–127 on |
| Legato | 1–64 off；65–127 on |

来源：p.7。低区在手册从 0 起列，实际不发送力度 0 的开关 note-on。

## 连奏、时序与专用动作

| 音乐音符力度 | 过渡速度 | 文档延迟（约） |
| --- | --- | --- |
| 1–64 | Slow | 220 ms |
| 65–100 | Medium | 130 ms |
| 101–127 | Fast | 90 ms |

来源：pp.3–4。短音到 rhythmic peak 约 60 ms（p.6）。这些是文档列出的过渡时间与节奏峰值时间。首音延迟需按当前 patch 单独确定。

- Sustain 与 Marcato 支持连接。Marcato 的 Repetition overlay 开启时，手册描述每次新音都可叠加 repetition；不要套用 CSB 只在 fast 连奏叠加的条件。来源：pp.3–4。
- Legato 关闭可演奏和弦；长音奏法独立保存 attack / release。延音踏板配合同音重复用于 re-tongue。来源：pp.4–5。
- Trills 使用半音 / 全音双键，起点间隔不超过 25 ms，任一键仍按住即可持续。来源：p.5。
- Flutter Tongue 的正文范围是 Flutes、Alto Flute、Piccolo，不能外推到双簧管、单簧管、巴松。来源：p.5。
- p.8 列出 Measured repetitions，但正文未充分说明全部参数；先保留该命令身份，再核对当前 patch 的同步与重复机制。
- Mix 与独立麦克风互斥。CSW 有 Close、Overhead、Main、Room 加 Mix 的配置；保留实际已载入通道与路由，不静默省略 Overhead。来源：p.2；[官方产品页](https://cinematicstudioseries.com/woodwinds/)。

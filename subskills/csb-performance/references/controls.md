# CSB 专用控制参考

参考 8 页版 CSB Manual。手册未标注脚本构建，请结合项目确认实际版本及所选 patch 可用的奏法。

## 默认控制

| 控制 | 本库含义 | 来源 |
| --- | --- | --- |
| CC1 | 长音动态；短音 selector 默认可用它选择类型 | pp.3、6–7 |
| CC11 | Config 图中的 Volume，可重映射 | p.7 图 |
| CC58 | 下列离散命令，可重映射 | pp.7–8 |

所读 Config 只有这三项映射，不据同系列其他库加入 CC2 / CC5 的含义。

## 默认 CC58 命令

| 闭区间 | 动作 |
| --- | --- |
| 0–10 | Sustain |
| 11–15 | Repetitions |
| 16–20 | Staccatissimo |
| 21–25 | Staccato |
| 26–30 | Sfz |
| 31–40 | Muted short notes |
| 41–45 | Rips |
| 46–50 | Trills |
| 51–55 | Flutter Tongue |
| 56–60 | Muted long notes |
| 61–65 | Double Tongue |
| 66–70 | Marcato，无 Repetition overlay |
| 71–75 | Marcato，有 Repetition overlay |
| 76–80 | Legato On |
| 81–85 | Legato Off |

来源：p.8。86–127 未列命令，不补造 Con Sordino。各动作仍以当前乐器实际载入的奏法为前提。

## 音符 keyswitch 自身的力度

先核实数字键号，实际 note-on 力度使用 1–127。

| 开关 | 力度与动作 |
| --- | --- |
| Staccato | 1–32 Repetitions；33–64 Staccatissimo；65–96 Staccato；97–127 Sfz |
| Muted | 1–64 muted short；65–127 muted long |
| Marcato | 1–64 Repetition overlay off；65–127 on |
| Legato | 1–64 off；65–127 on |

来源：p.7。手册从 0 起列的低区不要求实际发送力度 0。

## 连奏延迟与文档勘误

| 音乐音符力度 | 速度 | 乐器 / 文档过渡延迟（约） |
| --- | --- | --- |
| 1–64 | Medium | 小号 180 ms；圆号、长号、大号 230 ms |
| 65–127 | Fast | 100 ms；仍允许按具体乐器响应核对 |

p.3 正文把 fast 写成 65–100；p.4 的完整速度图和 Marcato 正文都写 65–127。本表按 p.4 的图及正文交叉核对，保留这项来源差异。不要生成三档速度或把高力度段当作未定义。

短音到 rhythmic peak 约 60 ms，来源 p.6。以上不代表首音延迟或实际音频测量；整轨混用奏法时分别补偿。

## 专用动作与保存状态

- Marcato 有两档连接速度；开启 Repetition overlay 后，fast（65–127）的新连奏音叠加 repetition。这个条件与 CSW 不同。来源：p.4。
- 延音踏板配合同音再触发用于 re-tongue。Legato 关闭可演奏和弦，长音奏法分别保存 attack / release。来源：pp.4–5。
- Trills 由相差半音 / 全音的两个音乐音触发，起点间隔不超过 25 ms；任一键按住仍可持续。来源：p.5。
- Double Tongue 可用宿主同步或手动速度；重复次数为 2–9，另有 X（手动短句触发）和 Hold（持续至松键）模式。保留实际模式，不再无条件把每次内部吐音写成独立 MIDI。来源：p.6。
- Muted short、Muted long 和 Flutter Tongue 分开核实当前 patch 可用性。弱音短音不作为持续长音处理。来源：pp.5、7–8。
- Mix 与独立 Close / Main / Room 互斥；每个激活麦克风有自己的路由，关闭会卸载采样。来源：p.2；麦克风名称另见 [官方产品页](https://cinematicstudioseries.com/brass/)。

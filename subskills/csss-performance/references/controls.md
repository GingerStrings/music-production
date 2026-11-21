# CSSS 专用控制参考

参考 8 页版 CSSS Manual。手册未标注脚本构建，请结合项目确认实际版本、主 patch 或 Classic Legato 及控制器重映射。

## 默认控制

| 控制 | 本库含义 | 来源 |
| --- | --- | --- |
| CC1 | 长音动态；短音面板默认可用它选择短音类型 | pp.3、6–7 |
| CC11 | Config 图中的 Volume，可重映射 | p.7 图 |
| CC2 | vibrato / non-vibrato；0 为 non-vibrato，手册明确为 on/off，不能中间混合 | p.5、p.7 图 |
| CC5 | Portamento On/Off；触发力度上限由 Portamento Velocity 决定，默认阈值为 20（包含 20） | pp.4、7 图 |
| CC58 | 下列离散命令，可重映射 | pp.7–8 |

Config 正文提到 Portamento Volume，截图标为 Portamento On/Off；按当前 patch 核对，不将 CSS 的连续音量语义移入本库。手册没有给出 CC5 开关的数值边界，不自行填写阈值。

## 默认 CC58 命令

| 闭区间 | 动作 |
| --- | --- |
| 0–5 | Sustain / Standard Legato |
| 6–10 | Sustain / Advanced Legato |
| 11–15 | Spiccato |
| 16–20 | Staccatissimo |
| 21–25 | Staccato |
| 26–30 | Sfz |
| 31–35 | Pizzicato |
| 36–40 | Bartok snap |
| 41–45 | Col Legno |
| 46–50 | Trills |
| 51–55 | Harmonics |
| 56–60 | Tremolo |
| 61–65 | Measured Tremolo |
| 66–70 | Marcato，无 Spiccato overlay |
| 71–75 | Marcato，有 Spiccato overlay |
| 76–80 | Legato On |
| 81–85 | Legato Off |
| 86–90 | Con Sordino On |
| 91–95 | Con Sordino Off |

来源：p.8。96–127 未列命令；不能因 CSS 的同值有新版本行为就改写 CSSS。

## 音符 keyswitch 自身的力度

先核对数字键号。下表将手册从 0 起列的低力度区改写为实际 MIDI note-on 的 1 起点。

| 开关 | 力度与动作 |
| --- | --- |
| Sustain | 1–64 Standard；65–127 Advanced |
| Staccato | 1–32 Spiccato；33–64 Staccatissimo；65–96 Staccato；97–127 Sfz |
| Pizzicato | 1–41 Pizzicato；42–84 Bartok snap；85–127 Col Legno |
| Marcato | 1–64 overlay off；65–127 overlay on |
| Legato / Con Sordino | 1–64 off；65–127 on |

来源：p.7。这些是 keyswitch 力度，不是短音 selector CC 值，也不是音乐音符的连奏速度表。

## 连奏、时序与专用动作

| 模式 / 对象 | 文档支持 |
| --- | --- |
| Advanced 过渡 | 音符力度 1–64：约 333 ms；65–100：约 250 ms；101–127：约 100 ms |
| Standard | medium / fast 两档；手册未完整另列其力度边界，不自行沿用 Advanced 三档表 |
| Classic Legato patch | 独立 patch；主 patch 的时间表不直接套用 |
| 短音 | 到 rhythmic peak 约 60 ms，分别处理起句与其他奏法 |

来源：pp.3–4、6。低力度还可能受 portamento 阈值覆盖；不要为做渐弱而意外写入滑音。以上是手册近似值，首音及真实起音需要另有依据。

- 长音 Legato 开启时是单音连接，关闭后可演奏和弦；各长音奏法分别保存 attack / release。延音踏板配合同音再触发实现 re-bow。来源：pp.3–5。
- non-vibrato 连奏是 re-bowed，vibrato 连奏是 slurred；切换振音还会改变过渡的演奏性质。来源：p.5。
- Trills 用相差半音 / 全音的两个音乐音，起点间隔不超过 25 ms；只剩其中一键按住也可持续。来源：p.5。
- Marcato 的动态主要由 mod wheel 控制，音乐音符力度还能细微强调；Spiccato overlay 状态单独处理。不要复制 CSS 1.7 的 >75 重音规则。来源：p.6。
- Measured Tremolo 一次触发含两次音，第二次受宿主或手动速度控制。来源：p.6。
- Con Sordino 为整 patch 的模拟处理；Mix 与独立麦克风互斥，关闭麦克风会卸载其采样。来源：pp.2、7。

官方补充：[CSSS 产品页](https://cinematicstudioseries.com/solo-strings/)。界面与 CSS 接近不构成脚本或控制响应等同的证据。

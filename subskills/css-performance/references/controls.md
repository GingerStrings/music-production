# CSS 控制与版本参考

参考 CSS 1.5 与 1.7 的 CSS Manual（各 8 页）及 CSS v1.7 Release Notes（3 页）。按实际加载的 patch 版本选择下表。

## 默认控制与版本边界

| 控制 | 对应功能 / 限制 | 来源 |
| --- | --- | --- |
| CC1 | Sustain 等长音动态；短音面板可把它用于类型选择 | 两版手册 pp.3、6–7 |
| CC11 | Config 图中的 Volume，可重映射 | 两版手册 p.7 图 |
| CC2 | Vibrato X-Fade；1.7 的 Sustain 可连续混合 non-vib / vib，禁用该映射时固定最大振音 | 两版手册 pp.5、7；1.7 notes p.3 |
| CC5 | Portamento Volume；触发仍取决于 Portamento Velocity，默认阈值 20，包含力度 20 | 两版手册 pp.4、7 |
| CC58 | 下表中的离散命令，可重映射 | 两版手册 pp.7–8 |
| CC59 | 1.7 加入的 RR reset；需要固定短音 RR 序列时才设置，不规定通用固定值 | 1.7 notes p.2 |

1.5 在 CC2=0 时使用模拟的 non-vibrato 连奏过渡；1.7 改进了相关过渡和交叉渐变。CSSS 的振音开关行为不用于 CSS。来源：1.5 手册 p.5、1.7 notes p.3。

## 默认 CC58 命令

范围均为闭区间；每次从所需范围内选择一个值。适用已载入相应奏法的当前预置。

| 值 | 1.5 | 1.7 手册 |
| --- | --- | --- |
| 0–5 | Sustain / Standard | Sustain / Low Latency |
| 6–10 | Sustain / Advanced | Sustain / Expressive |
| 11–15 | Spiccato | Spiccato |
| 16–20 | Staccatissimo | Staccatissimo |
| 21–25 | Staccato | Staccato |
| 26–30 | Sfz | Sfz |
| 31–35 | Pizzicato | Pizzicato |
| 36–40 | Bartok snap | Bartok snap |
| 41–45 | Col Legno | Col Legno |
| 46–50 | Trills | Trills |
| 51–55 | Harmonics | Harmonics |
| 56–60 | Tremolo | Tremolo |
| 61–65 | Measured Tremolo | Measured Tremolo |
| 66–70 | Marcato，无 overlay | Marcato，无 overlay |
| 71–75 | Marcato，有 overlay | Marcato，有 overlay |
| 76–80 | Legato On | Legato On |
| 81–85 | Legato Off | Legato Off |
| 86–90 | Con Sordino On | Con Sordino On |
| 91–95 | Con Sordino Off | Con Sordino Off |

来源：两版手册 p.8。96–127 在表中未定义，不为其补造命令。1.7 手册 p.7 的正文仍出现旧模式名称；该页表格、p.8 表和更新说明使用新模式名称。

## 音符 keyswitch 自身的力度

仅在数字键号已经核实时使用。以下范围写成可发声的 1–127；原手册低区从 0 起列。

| 开关 | 力度与动作 |
| --- | --- |
| Sustain | 1–64 选择 Standard（1.5）/ Low Latency（1.7）；65–127 选择 Advanced / Expressive |
| Staccato | 1–32 Spiccato；33–64 Staccatissimo；65–96 Staccato；97–127 Sfz |
| Pizzicato | 1–41 Pizzicato；42–84 Bartok snap；85–127 Col Legno |
| Marcato | 1–64 overlay off；65–127 overlay on |
| Legato / Con Sordino | 1–64 off；65–127 on |

来源：两版手册 p.7。1.7 表格沿用了 Spiccato Overlay 的旧称；其新 Marcato 行为另按下节处理，不据此认定与 1.5 完全相同。

## 连奏时间与专用动作

| 模式 | 已列出的过渡延迟（约） |
| --- | --- |
| 1.5 Advanced / 1.7 Expressive | 力度 1–64：333 ms；65–100：250 ms；101–127：100 ms |
| 1.5 Standard | medium / fast 两档；旧 Standard 的约 250 ms 由 1.7 notes 对照说明，不作为所有力度的统一值 |
| 1.7 Low Latency | medium 约 150 ms，另有 fast；手册未完整另列该模式的力度边界，不套用三档表 |
| Classic Legato patch | 与主 patch 分开；所读手册未给足独立时间表 |
| 短音 | 到 rhythmic peak 约 60 ms；与首音物理起音、长音过渡分开 |

来源：两版手册 pp.3–4、6；1.7 notes p.1。滑音阈值启用时，落入低力度区的连接还可能触发 portamento。没有音频实测时，以上值只用于有标记的初始补偿。

- Legato 关闭可演奏和弦，各长音奏法独立保存 attack / release。延音踏板配合同音再触发用于 re-bow；不要用长重叠代替同音重奏。来源：手册 pp.4–5。
- Trills 使用相差半音 / 全音的两个音乐音，起点间隔不超过 25 ms；任一键仍按住时颤音可继续。对这对音不要施加会破坏触发窗口的错开。来源：p.5。
- 1.7 Marcato 支持连贯快速跑句；音乐音符力度 >75 可形成局部强调。1.5 Marcato 的力度 / overlay 行为按旧版 pp.6–7 保留。来源：1.7 手册 p.6、notes p.1。
- Measured Tremolo 每次触发内含两次音，第二次按宿主速度或手动速度安排；先核实同步设置，再决定是否还需显式重复 MIDI，避免重复生成。来源：两版手册 p.6。
- Con Sordino 是整 patch 的模拟处理。Mix 与单独麦克风互斥；1.7 分开控制 Spot 1 / Spot 2。来源：手册 pp.2、7；1.7 notes p.2。

官方补充：[CSS 产品页](https://cinematicstudioseries.com/strings/)、[1.7 发布说明](https://cinematicstudioseries.com/assets/CSS%20v1.7%20Release%20notes.pdf)、[1.7.1 更新说明](https://cinematicstudioseries.com/updates/)。新版本需要核对本次保存状态，不自动替换旧项目的库版本。

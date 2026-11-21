# TSS 2.0 控制、奏法与音色状态

参考 Tokyo Scoring Strings Complete 的 27 页版手册，Instrument Version 2.0.0。以下页码采用 PDF 页号。

## 已有依据的控制

| 对象 | 文档规则与实现边界 | 页码 |
| --- | --- | --- |
| Dynamics | 手册以 CC1 / Mod Wheel 进行动态自动化；依奏法混合已录动态层，只有一个动态层时主要改变音量 | 7、20 |
| Vibrato | 只作用于 Arco；Non Vib、Vibrato、Molto 连续混合。所读手册未指定默认 CC 编号，按当前 MIDI Learn / 自动化映射接入 | 7、24 |
| Volume / Expression | 手册列出各奏法 Volume 和 Mixer；没有据此确认全局 CC11 映射，不填入 CS 系列的默认值 | 12、19 |
| CC64 | 可用于 Map 的 Ped Down / Up 条件；Easy Artic 中明确以值 127 选择 portamento 变体，详见播放参考 | 9、11 |
| Velocity Speed | 启用后，高音乐音符力度选择较快的连奏速度；未给出完整速度力度分区 | 7–8 |
| Niente | 开启后 Dynamics 可降到无声；关闭时最低为 pp | 10 |
| Range | 改变动态范围；影响 Dynamics 数值与输出的关系，不能当作单独的轨道音量 | 7 |
| Aftertouch | AT→Dynamics、AT→Vibrato 启用时分别连接到动态 / 振音；检查与 CC 自动化的共同影响 | 10 |
| Con Sord | 根据真实弱音录音的 EQ 曲线模拟弱音；其实际控制映射须核对 | 6 |

MIDI Learn 和自动化分配属于保存状态。文档未给出 TSS 的固定 CC58 奏法命令表；不要发送 CSS / CSSS / CSW / CSB 的命令值来控制它。

## Map 规则与示例键位

每个奏法最多三条 Map 规则。保存其完整条件、锁存方式、组合和实际优先级；不要只保留一个键名。KS 是控制键，Key 范围约束实际发声音；两者分别记录。Latching keyswitch 释放后仍保持选中。Legato Enabled 关闭的奏法不触发 Legato / Portamento。来源：pp.11–14。

下面是手册 Violins I 界面示例，供出厂映射参考。应用到现有工程前，核对对应 patch 的 Map；生成明确采用这套映射的 MIDI 时同时列出状态要求。C-2 对应 MIDI 0，C3 对应 MIDI 60；键名转换基于手册自己的八度约定（p.11）。

| 奏法 | 手册 KS | MIDI 键号 | 示例中的音乐音符力度条件 | 来源 |
| --- | --- | --- | --- | --- |
| Arco | C-2 | 0 | 图中未另列 | p.14 |
| Sforzando Long | C#-2 | 1 | 图中未另列 | p.17 |
| Sforzando Short | D-2 | 2 | 图中未另列 | p.17 |
| Decrescendo Long | D#-2 | 3 | 图中未另列 | p.17 |
| Decrescendo Short | E-2 | 4 | 图中未另列 | p.17 |
| Staccato | F-2 | 5 | 图中未另列 | p.17 |
| Staccatissimo | F#-2 | 6 | 图中未另列 | p.17 |
| Spiccato | G-2 | 7 | 图中未另列 | p.17 |
| Spiccato Secco | G#-2 | 8 | 图中未另列 | p.17 |
| Pizzicato | A-2 | 9 | 图中未另列 | p.17 |
| Harmonics | A#-2 | 10 | 图中未另列 | p.14 |
| Tremolo | B-2 | 11 | 图中未另列 | p.14 |
| Trills HT | C-1 | 12 | 图中未另列 | p.14 |
| Trills WT | C#-1 | 13 | 图中未另列 | p.14 |
| Legato Bow | F-1 | 17 | 80–127 | p.16 |
| Legato Slur | F-1 | 17 | 20–79 | p.16 |
| Lyrical Legato | F#-1 | 18 | 20–127 | p.16 |
| Run Legato | G-1 | 19 | 20–127 | p.16 |
| Marcato Legato | G#-1 | 20 | 20–127 | p.16 |
| Porta Bow | A-1 | 21 | 1–19 | p.16 |
| Porta Slur | A#-1 | 22 | 1–19 | p.16 |

图中这些 KS 均标为 Latching。上表的力度是音乐音符的规则条件，不代表开关音自身的力度，也不用于 Easy Artic 分区。Rebow 在 p.16 图中没有列出独立 KS，不补造键号；14–16 等未列键号也保持未定义。

## 演奏含义、音头与释放

- Legato Bow 换音同时换弓；Slur 同弓换音；Rebow 连接同音重复；Lyrical 含轻微滑音；Run 用于快速连接；Marcato 随力度、动态和速度改变攻击感。Porta Bow / Slur 分别保留换弓 / 同弓滑音的区别。来源：pp.16–17。
- HT / WT Trills 是单独的奏法。手册没有给出 CS 系列的“双键 25 ms”触发规则，不把那套事件组织搬到 TSS。来源：pp.14–15。
- Smart Attack 开启时，力度 1–49 保留正常音头，50–79 叠加 Staccato，80–127 叠加 Staccatissimo；overlay 的 Volume 与 Vel→Vol 另有设置。与 Easy Artic 的力度重标定共同使用时，实际作用按当前状态核对。来源：p.12。
- Bow Layer 是随力度和连奏速度变化的 Staccatissimo 叠层；短音 Dynamic Table 可重设力度到动态层的映射。因此同一力度的音头 / 音量会受这些保存设置影响。来源：p.13。
- Sound Offset 的单位是采样点；0 从自然音头播放，正值裁掉前段录音。不要把它当作 MIDI 轨道的毫秒提前量。Volume、ADSR、Offset 按各奏法分别保存。来源：p.12。
- Release 有 Natural、Excited、Staccato、Decrescendo、Harmonics；默认只启用 Natural，可按 Map 规则使用其他类型。选中奏法、已启用载入、允许连奏和 Release 规则分别确认，note-off 后保留需要的释放。来源：pp.11–15。
- p.17 末段标题将 Decrescendo 与 Sforzando Short 混写；该页界面和 p.9 时长表均把 Decrescendo Long / Short 独立列出，保留这一区分。

## Mix 与路由

Anima、Board、Cinema 是三套已混合的音色选择；Mic Mixer 提供 Close、Decca、Side、Back。按用户意图与当前保存状态选择，不能把它们仅当作文件名变化。Mic Mixer 可组合麦克风；CS 系列的 Mix / 独立麦克风互斥规则不用于判断 TSS 的 Mixer。来源：pp.4、22。

Mixer 使用 Console FX Rack & Mixer，完整恢复时保留各通道、效果器和主输出。需要修改该信号链时再读手册 p.19 引用的 [Console 官方手册](https://impactsoundworks.com/docs/ISW%20Console%20Manual.pdf)，不按截图猜测所有效果参数。

按实际 NKI 确认分组、Ensemble 与 Mix 变体。文件可定位、采样完整性、插件载入和实际发声分别核对；现有 NKI 清单不能证明某个工程的槽位或路由已经恢复。

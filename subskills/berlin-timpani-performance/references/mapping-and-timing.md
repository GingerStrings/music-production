# Berlin 定音鼓：键位、左右手与时序

参考 51 页版 CAPSULE User Guide BPC Timpani。页码均为 PDF 页码；输入范围的补充来自供应商的 Kontakt 版 [The Timpani Notes](https://orchestraltools.helpscoutdocs.com/article/362-berlin-percussion-the-timpani-notes)。其他播放器版本采用自己的映射。

## 槌与输入映射

Normal、Soft、Hard、Impact、Baroque 五种槌在手册 PDF p.10 明确列出。Single Hits 还包含分开的左右手采样；手册没有完整说明每个输入音对应的手、鼓和实际响音，需从当前 patch / 既有映射确认，不能只凭谱面音区猜测。

以下为官方 Kontakt Notes 的 Single Hits 输入范围、录制动态层数量及 RR 数量，作为产品参考：

| 槌 | 文档输入范围 R | 动态层 L | RR |
| --- | --- | --- | --- |
| Normal | C2–B5 | 7 | 5 |
| Soft | C2–B5 | 4 | 2 |
| Hard | C2–B5 | 5 | 4 |
| Impact | C2–B5 | 2 | 4 |
| Baroque | C2–B5 | 4 | 3 |

R 是供应商输入范围标签，不直接当成鼓的实际响音音域。映射记录至少区分输入 MIDI 编号、响音、左右手、槌 / 奏法及 patch 的 <TR> 移调；同音的不同输入键可能承担不同动作，但未核实前不填具体对应。当前构建或重映射与参考不符时使用本次证据。

CAPSULE 的 <TR> 会移动可弹奏范围，同时保留 keyswitch 等非发声键；Controller Table 中发生键位冲突时，分配还可能自动移动一个八度。修改后读取实际键号，不把原键名继续当作有效命令。来源：PDF pp.17、26。

## 单击、滚奏与录制动态句

- 在单击、录制 Rolls、显式交替击奏之间按音乐意图选择。只有写入已核实的左右手输入或对应 RR 行为后，才报告实现了该处理；随机错开同一组输入不能证明手分配正确。
- 录制的 Forte-Piano、Crescendo、Diminuendo、Accented Roll 等有自己的动态进程。先确定当前完整 patch 身份，再决定是否追加动态控制，不根据文件序号自动互换奏法。
- 要求按节拍展开的显式重复音，保留每次击奏的时间、力度、手与制音；使用录制 repetitions 时，确认内部已包含的击奏，避免同样节奏再写一层重复 MIDI。
- 不同单击与滚奏的门长 / 释放语义由当前奏法决定。谱面延音、MIDI gate、踏板持音和采样尾声分别保留。

## 速度、TM 与对齐

| 设置 | 文档行为 | 实现边界 |
| --- | --- | --- |
| Lock to Host | 跟随宿主速度，包括播放中的变速 / 渐变 | 渲染器须实际提供 tempo，MIDI 拍转秒不等于传入宿主速度 |
| Manual Tempo | Lock to Host 关闭后使用手动速度 | 保存所用 BPM 与控制曲线 |
| Auto Tempo / Tempo Slider | 自动或手动选择相应倍速 / 半速 / 三连感 | 不根据原始录音文件名强制工程 BPM |
| Lock to Beat | 让采样从下一拍开始 | 属于引擎量化，不能当作固定发音延迟而盲目提前所有事件 |
| TM Slider | TM patch 实时改变采样长度，保留释放样本 | 根据目标持续时长和当前模式处理；变化可能产生 TimeMachine 伪影 |

来源：PDF pp.16、29–30。常规短 / 长奏法不一定有全部同步功能。手册没有给出全库统一的起音毫秒表；只对有依据的奏法作补偿，不采用 CSS 的短音 60 ms 或 TSS Lookahead 数值。

## Multi：槽位与切换

Multi 最多 12 槽，Poly KS 最多同时选择 4 槽。完整保留槽位里实际的奏法、键位与发声范围，不能用 Multi 的合并键盘范围证明每个槽都能在同一键位发声。来源：PDF pp.31–35。

| 模式 | 行为 / 保存要求 |
| --- | --- |
| KS Mono | 以单个 keyswitch 或已分配的 Slot Switch CC 选槽；新槽从下一次音乐音符生效 |
| KS Poly | 可同时选多个槽；新选择在先前发声音符全部释放后对后续音生效，已有声音不被直接切断 |
| Vel Switch / CC Switch | 按力度或 X 轴 CC 切换所选槽，可有自定义阈值 |
| CC XFade / 2D XFade | 在所选槽间混合，2D 使用 X / Y 两轴；不是相同的离散切换 |
| Locked View | 冻结当前配置并 purge 未使用样本；手册规定配置更改受限，不能仅凭发送配置 CC 报告状态已改变 |

默认 Multi 分配：Vel Switch Mode 为 CC25，CC Switch Mode 为 CC26，CC XFade Mode 为 CC27，2D Mode 为 CC28；X Fade/Switch 为 CC22，Y Fade 为 CC23。Slot Switch CC 默认为未分配。以上均需按当前 Controller Table 核对，手册未提供可直接套用的全套槽位编号到 CC 值转换。来源：PDF pp.47–48。

Preset 系统保留适用的音色与 Mixer 设置，却不恢复 Multi 里已经载入的奏法。恢复 Multi 要保留完整插件状态或另有明确槽位数据，不能只加载同名 preset。来源：PDF p.15。

中段回放或分块时保留有效槽位选择、锁存 / 混合状态、CC64、动态、RR 和同步设置。需要实际声音验证时检查受影响部分及尾音；本子技能的创建只使用文件和文档。

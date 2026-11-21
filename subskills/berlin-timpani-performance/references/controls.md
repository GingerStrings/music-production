# Berlin 定音鼓：控制、力度与制音

参考 CAPSULE User Guide BPC Timpani，51 页，Rev. 2016-04-13。以下均为 PDF 页码，例如 PDF p.13 是印刷页 12。该手册含 CAPSULE 各产品的通用示例，Used by 与当前 patch 的 INACTIVE 状态共同限定适用范围。

## 默认控制分配

下表记录控制器的出厂分配，现有 Controller Table、启用状态、曲线和重映射优先。表内 Off 表示未分配控制器，不能用来判断对应功能开关的当前值。

| 功能 | 文档默认分配 | 条件 / 来源 |
| --- | --- | --- |
| Main Knob X-Fade | CC1 | X-Fade 模式下跨力度层；PDF p.13 |
| XFade/Velocity Mode | CC14 | Single Articulation 的力度模式切换；PDF p.38 |
| Instrument Vol.1 | CC7 | Kontakt 音量 / 平衡；PDF pp.13、38 |
| Instrument Vol.2 | CC11 | Expression，总体音量；PDF pp.13、39 |
| Sustain Pedal | CC64 | 实际持音、释放及 True Damping 按当前奏法；PDF pp.13、39 |
| Soft Release | CC15 | 对当前声音的 Soft Release；PDF p.39 |
| True Damping | Off | 仅支持此功能的 BPC 奏法，PDF p.39 |
| Dynamic Switch | Off | 仅支持的 velocity-controlled 键，PDF p.39 |
| Tempo Mode | CC50 | 使用时间伸缩的 patch，PDF p.42 |
| Manual Tempo | CC51 | Lock to Host 关闭时；PDF p.42 |
| Time Stretching | CC51 | TM patch 的对应参数；PDF p.44 |
| Attack | CC73 | 实际可用的音头参数，PDF p.43 |
| Attack Curve | CC74 | 实际可用的音头曲线，PDF p.44 |
| Release | CC72 | 实际可用的释放参数，PDF p.44 |
| RR Reset Key | A-1 | 供应商键名；发送前确认 MIDI 数字键号，PDF p.42 |
| CC115 | 内部 Purge 用途 | 保留内部映射，不用于演奏控制或外部重新分配，PDF p.13 |

CC51 在 Manual Tempo 与 TM 中具有不同上下文。控制曲线、参数单位和实际生效项都要按 patch 确认，不将输入值直接当作 BPM 或毫秒。文档没有给出所有开关的数值阈值，不补造统一边界。

## 力度模式

- Main Knob 的 Velocity 模式使用击键力度；X-Fade 模式使用所分配的 CC。部分奏法固定 X-Fade，需按当前 patch 判断。来源：PDF pp.27–28。
- Dynamic Switch 在 velocity-mapped 键上按分界切换录制动态层，取代动态层之间的 crossfade；不影响 X-Fade-controlled 键（如相应 Rolls）。来源：PDF p.50；[官方 CAPSULE 说明](https://orchestraltools.helpscoutdocs.com/article/100-standard-articulations)。
- CC11 与 CC7 调整音量，不自动重选击奏动态层。需要改变音头 / 演奏强度时，落实当前 Velocity 或 X-Fade 控制，再按句子安排电平。
- Niente、Soft Low Layer、Volume Range、Cutoff 与层的载入状态会改变响应。它们的可分配 CC 显示 Off 时，仍需读取功能本身的保存值。来源：PDF pp.22–23、42–44。
- 依当前 mallet / articulation 校准力度；不以不同 patch 相同 MIDI 数值推定相同音量或槌击强度。

## True Damping、持音与释放

Single Hits 录有普通与制音采样。启用 True Damping 时，CC64 未激活会使用录制的制音；CC64 激活允许声音继续自然延展。来源：PDF pp.10、50。

按需要的制音位置安排 note-off / 踏板，并确认当前 patch 的真实响应。需要自然余响时，短谱面音值不等于立即切断全部声音；需要止音时，单独降低 CC11 也不能证明触发了录制的制音动作。

Soft Release、Release 参数、True Damping 和已录制的 Muted Hits 分别处理。释放样本是否已 purge 会影响 Release 旋钮所控制的对象；不要通过统一缩短所有音符来代替这些功能。来源：PDF pp.19、23、39。

## RR、加载与 Mixer

RR 可有顺序 / 随机、Polyphonic RR、New Note Resets、空闲时间重置及启用层。Fake Neighbor RR 使用邻音采样移调，不能报告成额外录制的真实 RR。按当前 patch 可用性保留，只有需要确定序列时才安排 reset。来源：PDF p.24。

本库的 Close、Tree、Surround、A/B 可组合；每个通道有载入、音量、声像和输出。Auto Gain、Chain 与 Solo / Mute 会改变多麦克风之间的关系，不能仅靠四条推子数值重建完整输出。关闭通道可 purge 采样；恢复状态时区分参数存在与采样已加载。来源：PDF pp.10、18–21。

CAPSULE 表内的 Berlin Strings Con Sordino、其他库的振音 / 连奏等 Used by 条目不作为定音鼓功能。只有当前 patch 支持且实际启用的控制才进入演奏数据。

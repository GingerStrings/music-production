# TSS 2.0 播放模式与时序

参考 Tokyo Scoring Strings Complete 2.0.0 手册 pp.7–10、12–13、21。以下规则以当前 patch 已加载、相应功能已开启为前提；普通 Map 与 Easy Artic 分开处理。

## 模式选择与连接条件

| 模式 | 文档行为 | 操作含义 |
| --- | --- | --- |
| Zero Latency | 禁用真实 Legato 录音，Legato Speed 控件不起作用 | 可用于即时演奏 / 录入；不能据此报告真实过渡已实现 |
| Standard | 按当前 Legato 模式 / 速度播放，奏法可有自然 preroll | 按当前过渡与起音依据安排触发，不套用其他库的毫秒表 |
| Lookahead Full | 1000 ms 前瞻；可内部选择奏法、调整连奏与奏法时序 | 按任务选择 Easy Artic 和自动 Legato Speed，并核对宿主补偿 |
| Lookahead Short | 300 ms，功能受限 | Easy Artic 不可用；使用当前有效 Map 与允许的功能 |

来源：pp.8–10。1000 / 300 ms 是所读手册的前瞻窗口，不是四档连奏采样的逐音起音表。

Mono 以音乐音符重叠触发连奏。Poly 检测当前 Latency 窗口内的非重叠后继音；p.7 的 150 ms 是示例旋钮值，不是固定要求。Poly Legato 不适用于 Zero Latency。调整门长和呼吸时，检查连接是否仍满足当前模式，保留本次所需的声部关系。

Slow、Medium、Fast、Very Fast 四档速度由当前设置选择；Velocity Speed 可让力度影响档位，但手册未列完整阈值和固定毫秒值。Lookahead Legato Speed 则依据时间分析选择可容纳的过渡。启用自动选择后，不再无依据地添加另一套逐音速度控制或补偿。来源：pp.7–9。

## Easy Artic 的适用条件

仅在 Lookahead 中开启 Easy Artic，且 Short Mode 关闭时使用以下两张表。力度 1–63 是 Legato Region，64–127 是 Basic Region；实际输入力度在所属区域内重新缩放：63 是连奏区域的最大力度，64 是基本区域的最小力度。不能把低数值直接解释成弱奏。来源：p.9。

### Basic Region：力度 64–127

| MIDI 音符时长（手册列出的整数毫秒） | 选择的奏法 | 额外条件 |
| --- | --- | --- |
| ≤10 ms | Pizzicato | 正时值的音乐音符 |
| 11–200 ms | Spiccato Secco | — |
| 201–300 ms | Spiccato | — |
| 301–400 ms | Staccatissimo | — |
| 401–500 ms | Staccato | — |
| 501–700 ms | Decrescendo Short | 力度 127 改为 Sforzando Short |
| 701–900 ms | Decrescendo Long | 力度 127 改为 Sforzando Long |
| ≥901 ms | 默认 Arco | 已通过 KS 选中其他 Long（如 Tremolo、Trills、Harmonics）时保留该 Long |

表按 p.9 的整数毫秒边界记录；亚毫秒边界和实际量化方式未说明，不额外宣称某种取整算法。音符时值也决定奏法，量化、延长、gate humanization 或改变速度后要核对受影响的选择。

### Legato Region：力度 1–63

| 音乐音符力度 | 选择的过渡 |
| --- | --- |
| 1–15 | Lyrical Legato |
| 16–31 | Legato Slur |
| 32–47 | Legato Bow |
| 48–63 | Marcato Legato |

CC64=127 时手册说明使用 portamento 变体；时长小于 100 ms 的连奏音会改用 Run Legato。两项条件同时成立时，所读手册没有说明优先级，保留待核对，不补造映射。对半踏板 / 其他 CC64 值也不填入未列的边界。来源：p.9。

需要固定某种连奏 / 发音而 Easy Artic 条件无法准确表达时，可在本次音乐和保存状态允许的范围内采用明确 Map；保留选择依据，不为适配工具而更改音乐句子。

## 拍位、补偿与状态恢复

- Easy Artic 按实际 MIDI 持续时长选择。固定速度时 duration_ms = duration_beats × 60000 / BPM；变速时使用速度图的终点秒数减起点秒数，不只套一个局部 BPM。改变音符重叠或释放前，分别保留音乐时值与实际 gate。
- 前瞻窗口、宿主报告的延迟 / 补偿、采样自然 preroll、Poly Latency 和 Sound Offset 分开记录。先核对现有宿主与保存状态的处理，避免把窗口长度再作为整轨或逐音提前量重复施加。
- 所读手册没有证明当前独立宿主自动处理所有 TSS Lookahead 延迟。后台渲染沿用主技能流程，核对实际延迟信息、帧数、音符结束与尾音；不能仅凭正确拍位或模式名称宣称对齐。
- UI Parameter Sync 针对 Lookahead 中的参数同步，手册说明设置依赖 DAW。动态 / 振音错位时检查该设置与控制事件时间，不将音符和所有 CC 一起机械平移。来源：p.10。
- 中段开始、循环或连续分块时，保留 / 恢复当前模式、Map、锁存 KS、CC、踏板、速度选择、载入奏法、Release 与已经进行中的连接状态。依据实际状态恢复相关内容，不每块重置插件。
- Dynamics、Vibrato、Smart Attack、Dynamic Table 与 Easy Artic 的力度重标定可能共同影响输出。避免把音高以外的字段统一随机化；只修改本次有明确意图的音符和控制器。

## 验证范围

常规检查只确认本次实际用到的模式、事件和状态能表达要求。已有明确异常时，针对受影响边界做短片段对照；没有执行音源时，只报告文档支持与静态实现。创建本子技能不运行插件，也不生成声音或启动前台界面。

# Cell 映射与演奏

## 从具体鼓组建立映射

先确认实际 kit 和用户需要的鼓件。工厂库分类可帮助查找候选，不能代替当前音乐所需的采样选择。在项目工作目录记录以下触发参数。

| 资料 | 用途 |
| --- | --- |
| 实例、kit、cell 标识及鼓件角色 | 区分主鼓、叠层与辅助打击乐 |
| 接收通道、cell 的 MIDI 键区 | 按实际状态选择触发，不套用 GM |
| 各层 Low Vel / High Vel、采样引用 | 确认目标力度触发哪些层 |
| 触发条件、轮替规则与声音组 | 解释重复击打、条件触发和截断 |
| Key Track、Root、调音 | 保留有音高或固定音高的播放意图 |
| cell / layer 增益、输出目标 | 区分力度表达、音量与路由问题 |

跨软件使用 MIDI 数字键号 0…127，并记录通道编号采用 1…16 还是 0…15。不同软件的八度显示可能不同；以数字键号为准。正常 note-on 力度使用 1…127，零力度 note-on 按 MIDI 的 note-off 语义处理。

一个 cell 可有多个采样层，各层有独立力度范围，重叠区还可能有交叉淡化。层 Root 定义移调基准，须结合 Key Track 状态解释实际音高。保留已有叠层与交叉淡化；文件存在、层存在、条件满足及声音产生各有不同含义。[官方 Mapping Editor](https://docs.native-instruments.com/ni-tech-manuals/battery-manual/en/editor-page)

需要增加多采样时，区分“多个 cell”与“同 cell 多层”的导入方式；Loading 首选项的 Expand Over Multiple Cells / Merge In One Cell 会影响结果。避免为一次任务改动全局模板与首选项。静态处理采用明确保存的配置或已有适配器。[官方多采样说明](https://support.native-instruments.com/support/solutions/articles/69000879956-battery-how-to-load-multiple-samples-into-one-battery-cell)

## 力度、节奏与鼓件平衡

Velocity To Volume 决定力度影响音量的程度；设为 0% 时，力度不改变该模块的输出音量。力度仍可能通过映射选择其他层，因此应分别查看力度层与音量响应。[官方 Velocity 模块](https://docs.native-instruments.com/ni-tech-manuals/battery-manual/en/main-page)

先依据音乐分配重音与轻击，再结合实际采样、layer / cell / 总线增益调整平衡。不要把所有 kit 的镲片、辅助打击乐和底鼓统一为相同力度或峰值；极弱的辅助声部也可能需要单独增益。保留用户希望突出的节奏线索。信号统计能反映静音、峰值等事实，音色选择与混合听感继续按用户反馈调整。

真实原声鼓手的目标需要考虑手脚分配：tom fill 与密集军鼓占用双手时，相应安排踩镲、ride 和其他同时击打。电子鼓、层叠打击和有意的机械节奏按其声音设计处理。段落、BPM、切分、微时差、fill 密度与是否随机变化都由当前作品决定。

## 释放与踩镲互斥

单次采样可能在 MIDI note-off 后继续播放尾音。需要随离键收束时，启用 Volume Envelope 并选择 **AHDSR**，按声音设定 Sustain / Release；AHD 不提供这项释放控制。出现断音点击时调整释放时间，保留有意的切片效果。官方示例数值只用于示范，不作为所有鼓件默认值。[官方 note-off 说明](https://support.native-instruments.com/support/solutions/articles/69000879954-how-to-set-up-battery-to-play-a-sample-until-the-midi-note-is-released)

开放 / 闭合踩镲需要互斥时，先读取已有声音组。官方新建示例将两者分到同一新 Voice Group、Voices=1，并为闭镲设置 Trigger=Note On、Condition=Cycle Round Robin、Position=1。按具体 kit 确认这套设置；勿把底鼓、军鼓和其他需要同时发声的 cell 放入同一单声部组。它解决的关系是击打之间的截断，另需保留恰当的释放与采样尾音。[官方踩镲互斥示例](https://support.native-instruments.com/support/solutions/articles/69000879959-how-to-set-up-battery-4-cells-for-hi-hat-choking)

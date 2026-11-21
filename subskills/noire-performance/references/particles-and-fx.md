# NOIRE Particles 与效果状态

参考 24 页版 NOIRE Manual 的 PDF 第 12–23 页。这里只处理用户任务实际使用的生成层和信号路径；不规定作品必须采用或关闭这些功能。

## Particles 是生成层

Particles 根据输入按键生成额外音符 / 声音。它可以用于伴奏、琶音、脉冲和云状织体；生成的声音不等同于原始 MIDI 轨里的新增音符。来源：pp.4、15–16。

| 设置 | 文档行为 | 实现边界 |
| --- | --- | --- |
| Engine / Preset | 开关和预设决定生成层的基本状态 | 保存真实开关和预设，不只记录名称 |
| Mix | 最左只保留钢琴，最右只保留 Particles | 输入 MIDI 有音而缺少钢琴本体时，先检查 Mix |
| Sync / Density | Sync 将生成序列同步到速度，Density 此时使用音符值 | 实际宿主速度与 MIDI 秒制调度分别确认 |
| Variation | 改变生成事件间隔；同步时仍会引入变化 | 不宣称随机生成层逐次导出完全相同 |
| Pre Delay | 开启后，生成云在钢琴第一音之后开始；关闭时同时开始 | 属于声音设计的生成时间，不作为宿主补偿 |
| Decay | 调整按键触发后的衰减长度；Infinite 时持续至全部按键释放 | 确认真实释放条件，结尾保留所需尾声 |
| Engine Mode | 改变触发的音区、八度及音色方式 | 修改后核对其额外音高，不能只看输入 MIDI |

来源：pp.16–17。Decay 的具体值以当前状态为准，手册没有给出适用于所有 preset 的固定成品尾长。

Tonal Source 可选 Piano、Plucked、Brush、Mallet；Noise Source 可选 Combined、Mechanics、Felt、Soft Stick。混合量、Timbre、Attack 分别作用于生成源。Particles 还有独立 Filter / Diffusion，Diffusion 的 Delay 可按毫秒或同步音符值工作。来源：pp.18–19。

## FX、噪声与 Space

- EQ、Transient、Compressor、Stereo Image、Style 各有开关与参数。Transient 左侧强化音头、右侧延长持续；Style 的 Timbre / Moving / Continuous 用于不同声音处理。保留原有状态，不把它们统一当成后级音量。来源：pp.12–13。
- Noises to EQ 与 Noises to Style 控制噪声是否进入对应处理；默认分路与开启后的处理范围不同。钢琴音体被滤波并不证明全部噪声也已被处理。来源：pp.12–13。
- Ambience Noise 可连续存在；Pianist Noise 在演奏时触发，并可由 aftertouch 产生额外声音。排查额外响声时检查这些真实来源，不直接删改音乐音符。来源：p.14。
- Stereo Swap 改变低 / 高音的左右位置；Width 居中是原始宽度，向左到单声道，向右扩宽。保留用户指定的听音视角。来源：p.13。
- Space 包含卷积 / 算法混响和 Replika Delay。主界面 Reverb / Delay 旋钮控制发送量，对应模块须启用才有作用；它们与 Particles 的 Diffusion 分开。来源：pp.6–7、19–23。
- 同步的 Particles、Diffusion、Reverse Reverb 或 Delay 需要相应的 tempo / transport 条件。改变 BPM、同步开关、Time 或 Feedback 会影响实际结束时间；按保存状态渲染，不用同一个尾音常量裁切。

## 接入与验证

恢复插件状态时保留钢琴、生成层、噪声、FX / Space 与路由。用户只改音符或踏板时，不自动替换 snapshot 或移除有意效果。需要只含主钢琴的输出时，按本次要求选择相应状态，并区分它与完整音色。

所需后台宿主若不能表达同步参数或完整效果路径，说明实际缺口，继续完成可静态落实的事件和配置要求。声音生成后按主技能确认文件可读取、所需内容与尾音完整；本子技能本身不附加全曲逐事件或听感审查。

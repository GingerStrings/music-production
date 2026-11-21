---
name: tss-performance
description: "实现 Impact Soundworks Tokyo Scoring Strings（TSS，东京弦乐）Complete 2.0 的 Kontakt 演奏与音色配置；用于 Standard / Lookahead / Zero Latency、单音与复音连奏、Easy Artic、规则映射、动态振音和释放。"
---

# TSS 东京弦乐

将本次弦乐写作落实到实际 TSS 乐器、播放模式和保存状态。适用版本为 Tokyo Scoring Strings Complete 2.0.0，手册列出的最低要求为 Kontakt / Kontakt Player 7.8.1。其他版本请结合对应手册与工程状态核对。

先读 [Kontakt 共用操作](../../references/kontakt-library-workflow.md)。涉及奏法和表达时读 [TSS 控制与奏法](references/controls.md)；涉及音符连接、音长、延迟或 Easy Artic 时读 [播放模式与时序](references/playback.md)。

## 进入与实现

1. 确认五个分组或 Ensemble、Anima / Board / Cinema Mix 或 Mic Mixer、具体 NKI / snapshot、接收槽位 / 通道，以及已载入的奏法。保留用户选定的版本、音色和混音。
2. 继承当前播放模式，或按任务明确选择 Zero Latency、Standard、Lookahead；同时记录 Mono / Poly、Poly Latency、Easy Artic、Short Mode、自动 / 力度连奏速度和 UI Parameter Sync。只在相关条件匹配时使用对应表。
3. 普通映射按当前 Map 规则、keyswitch、力度条件和 Legato Enabled 状态组织事件。Easy Artic 改用自己的力度 / 音长 / CC64 规则；两套规则分开处理。
4. Mono 以音符重叠连接，Poly 以当前 Latency 窗口内的非重叠后继音检测声部；不要给两种模式统一增加相同重叠。不同声部需要独立 CC 表达时，仍使用独立接收通道 / 实例。
5. Dynamics、Arco Vibrato、短音 Dynamic Table、Smart Attack、Bow Layer、Release 和 Con Sord 分别按当前配置处理。修改音乐音符力度可能改变奏法、连奏速度、动态或音头，先检查涉及的机制。
6. 保存谱面位置与触发位置；Lookahead 的内部调度、宿主补偿和采样起音分别核对。所读手册没有给出四档速度的统一毫秒表，不采用 CSS / CSSS 的延迟值。

## 状态接入与交付

读写已有音色时保留 Map、MIDI Learn、每奏法 Sound 参数、Mixer / Console 效果及输出。读取 NKI 路径或说明所需设置不能替代插件状态恢复；没有经过验证的写入器时，复用已有正确状态，并说明仍缺的接入条件。

文件操作、后台运行、前台界面和 Computer Use 遵守共用操作及会话已有授权。单独创建本子技能不启动 Kontakt / DAW，也不调整安装或授权。按任务交付所需工程、MIDI、音频或谱面；验证只覆盖实际执行的范围。

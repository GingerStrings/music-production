---
name: berlin-timpani-performance
description: "实现 Orchestral Tools Berlin Percussion - The Timpani 的 Kontakt / CAPSULE 演奏与音色配置；用于五种槌、Single Hits / Rolls、True Damping、力度模式、RR、节拍同步、TM 和 Multi 槽位。"
---

# Berlin 定音鼓

将定音鼓击奏、滚奏、渐变、制音和换槌落实到实际 BPC A - The Timpani patch。参考 51 页版 CAPSULE User Guide，修订日期 2016-04-13；其表格列 Collection 1.0、CAPSULE 2.5、Full Kontakt 5.5.1+。实际工程版本、NKI 与脚本状态分别核对，其他播放器版本另用对应资料。

先读 [Kontakt 共用操作](../../references/kontakt-library-workflow.md)。控制器、动态与制音读 [控制与奏法](references/controls.md)；键位、左右手、节拍和 Multi 读 [键位与时序](references/mapping-and-timing.md)。

## 进入与实现

1. 确认 Normal、Soft、Hard、Impact 或 Baroque 槌，Single / Multi、普通 / TM patch、实际输入映射与响音，以及当前槽位 / 通道。按音乐需要选择单击、录制滚奏、动态短句或显式重复。
2. 读取 Main Knob 的 Velocity / X-Fade、Dynamic Switch、当前力度层和 Controller Table。击键力度、CC1、CC11、CC7 各按实际用途写入；不把一条动态曲线用于所有 patch。
3. 支持 True Damping 的奏法按开关、CC64 和音符释放组织制音；踏板允许自然延续的行为与钢琴的半踏 / 复踏不同。控制器分配显示 Off 不证明功能本体已关闭。
4. 左右手采样、输入键位和真实音高分别保留。需要交替击奏时以已核实的手映射写事件；增加随机偏移不能替代正确的双手 / RR 选择。
5. 滚奏、重复短句、渐强弱句和 TM 按当前同步、速度及门长实现。Lock to Beat 可延后到下一拍，不能套用弦乐固定提前量。
6. Multi 读取完整槽位、KS Mono / Poly、叠加 / 切换方式、阈值及 Locked View；其 KS Mono / Poly 选择的是槽位行为，不能等同于 TSS 的单音 / 复音连奏模式。

## 状态接入与交付

恢复实际 NKI / 组件状态时保留槌型、槽位内容、Controller Table / 曲线、动态层、RR、制音、麦克风与输出。CAPSULE preset 不恢复 Multi 的已载入奏法，不能仅凭 preset 名称报告槽位正确。

文件、后台运行、前台界面与 Computer Use 分别继承会话已有授权。按任务交付所需工程、MIDI、音频或谱面，说明仍缺的键位 / 状态依据；编写本子技能不运行插件或安装程序。

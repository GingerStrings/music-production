---
name: noire-performance
description: "实现 Native Instruments NOIRE Pure / Felt 的 Kontakt 钢琴演奏与音色配置；用于力度响应、延音 / 半踏 / 复踏、静默键、共鸣释音、Particles Engine 和效果状态。"
---

# NOIRE 钢琴

按本次钢琴与声音设计要求实现 NOIRE 演奏。参考 24 页版 NOIRE Manual；文档未明确标出库脚本构建，实际版本、NKI / snapshot 和重映射需从当前项目确认。

先读 [Kontakt 共用操作](../../references/kontakt-library-workflow.md)。演奏、踏板与音色处理读 [钢琴控制与踏板](references/piano-controls.md)；使用 Particles、同步效果或排查额外声音时读 [Particles 与效果](references/particles-and-fx.md)。

## 进入与实现

1. 确认 Pure 或 Felt、具体 snapshot、Kontakt 槽位 / 通道、Particles 开关与混合量，以及已有踏板和参数自动化。两套 NKI 对应不同的录音处理，按用户选择保留。
2. 音乐音符力度结合当前九种 Velocity Curve 之一、Color、Dynamics 和 Silent Key 设置处理。不要把管弦乐的 CC1 动态交叉渐变规则用于本库，也不要为修复静默键行为而无依据地整体抬高力度。
3. 延音采用已确认的 CC64 接收映射；半踏与复踏还须匹配 Half Pedal / Repedal 状态。保存 note-off、踏板及其先后关系，区分手指离键与实际声音结束；重复音、换踏和句尾各按音乐处理。
4. Release Samples、Resonance、Overtones、Attack、噪声和调律分别属于音色状态。保留有意的机械声、环境声与共鸣，不把所有附加声音统一当作错误。
5. Particles 能主动产生额外音符；选择声音类型、模式、Sync、Density、Decay 和 Mix 时保留音乐目的。需要逐音钢琴输出时检查它是否应启用；已有声音设计任务不自动关闭它。
6. 保留音符的音乐位置和触发位置。没有本预置的起音依据时，不套用弦乐提前量；同步效果需要真实宿主速度支持，输出保留踏板、共鸣和效果尾音。

## 状态接入与交付

读取或复制保存状态时保留钢琴设置、Particles、FX / Space、自动化和输出路由。参数名称、NKI 文件路径或 MIDI 本身不能证明正确音色状态已恢复；需要新设置时使用已有适配器或明确的已保存状态。

运行权限与交付遵守共用操作和会话已有授权。按任务提供工程、MIDI、音频或谱面，准确说明实际实现范围；编写本子技能不启动插件或前台界面。

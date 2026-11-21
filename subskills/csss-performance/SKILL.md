---
name: csss-performance
description: "实现 Cinematic Studio Solo Strings（CSSS）独奏弦乐的 Kontakt 演奏与音色配置；用于主 patch / Classic Legato、Standard / Advanced、离散振音、滑音和首席叠加。CSS 合奏弦乐使用 css-performance。"
---

# CSSS 独奏弦乐

将独奏、四重奏或首席叠加的音乐意图落实到实际 CSSS 预置。先读 [共用操作](../../references/kontakt-library-workflow.md)，写入控制事件前读 [CSSS 专用控制参考](references/controls.md)。

## 进入与实现

1. 确认独奏乐器 / Ensemble、版本、主 patch 或 Classic Legato、当前 Standard / Advanced 模式及重映射。当前参考只覆盖所读 CSSS 手册，不把 CSS 1.7 的模式改名或新功能移入本库。
2. 依据句子处理单线连奏、换弓、同音重奏、滑音和断开。需要同时独立表达的声部使用独立接收通道 / 实例。
3. 区分音乐音符力度与开关音力度，先决定是否允许 portamento，再选择连奏速度和相应近似补偿。Standard 与 Classic 的未列参数保留待核对。
4. CSSS 的 vibrato / non-vibrato 按手册是离散切换。不要把 CC2 绘成未经支持的连续振音深度；长音动态、Volume 和振音各自承担本库的实际功能。
5. 与 CSS 做首席叠加时分别配置连奏、振音、起音和释放；只复制同一份 MIDI 及 CC 不能保证两库动作一致。

谱面上的独奏弓法与实际触发分别保留。需要和弦时明确关闭单音 Legato，按预置能力及本次写作目标实现。

## 状态与交付

按任务继承或修改弱音器、包络、麦克风、输出和已载入奏法，不把首席叠加设为所有 CSSS 使用场景的要求。

工程、后台渲染和交付使用共用操作；实际状态无法确认时，完成已具备依据的部分，并说明缺少的映射或接入条件。

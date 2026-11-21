---
name: csb-performance
description: "实现 Cinematic Studio Brass（CSB）铜管的 Kontakt 演奏与音色配置；用于具体独奏 / 合奏乐器、两档连奏、乐器相关延迟、弱音、双吐和 Marcato overlay。CSW 木管和 CSS / CSSS 弦乐使用各自子技能。"
---

# CSB 铜管

将当前铜管声部的音头、持续支撑、吐音和释放落实到实际 CSB 预置。先读 [共用操作](../../references/kontakt-library-workflow.md)，写入控制事件前读 [CSB 专用控制参考](references/controls.md)。

## 进入与实现

1. 确认具体小号、圆号、长号 / 低音长号或大号，独奏 / 合奏 patch、版本、通道及重映射。不同乐器的过渡时间分开处理。
2. 按本库两档力度区选择连接速度。手册一处正文与图表不一致，采用参考页记录的完整图表依据；不要遗漏力度 101–127。
3. Sustain、Marcato、短音、Muted、Double Tongue 等分别落实触发与释放。Marcato overlay 的行为按当前库处理，不照搬 CSW 或 CSS 的条件。
4. 长音动态与 Volume 分开；短音先核对 selector，避免 CC1 曲线跨过类型分区。未有依据的振音 CC 不从其他系列复制。
5. 需要换气或重吐音时落实音符断开 / 同音再触发；使用已有 sfz / marcato 音头时，再根据句子判断所需附加动态。

## 状态与交付

明确当前 patch 的弱音与花舌等奏法是否可用。声部独立表达需要独立接收通道 / 实例；麦克风、包络和输出按实际状态保留或修改。

工程接入、运行权限和交付遵循共用操作。控制表有依据与音源已载入、实际发声分别表述。

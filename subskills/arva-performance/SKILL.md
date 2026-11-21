---
name: arva-performance
description: "实现 Strezov Sampling Árva Children Choir（Arva 童声合唱）的 Kontakt 演奏与音色配置；用于男童 / 女童与 divisi、独唱、True / Agile Legato、Syllabuilder 3 音节序列、CONNECT / MORPH 和自然起音处理。"
---

# Árva 童声合唱

按本次合唱编制、音节与连奏要求实现 Arva。Arva Manual 描述 Syllabuilder Engine 3。按当前 NKI 和已保存的设置确认合唱编制、音节模式和可用奏法。

先读 [Kontakt 共用操作](../../references/kontakt-library-workflow.md)。选声部、专用连奏与声部分配时读 [声部与连奏](references/voices-and-legato.md)；组织音节、调起音或保存配置时读 [Syllabuilder 与控制](references/syllabuilder-and-controls.md)。

## 实现要点

1. 确认男童 / 女童、Soprano / Alto、合奏 / 独唱、具体 NKI / snapshot、Kontakt 槽位和接收通道。需要独立声部与动态时分开实现，保留用户选择的人数感与音色。
2. 区分专用 Ah / Mm / Ooh True Legato patch 与 Syllabuilder 的 Agile Legato。前者对应录制的元音连奏，后者让音节序列参与复音连接；当前 patch 的开关和模式分别确认。
3. Syllabuilder 使用库内录制音节构造序列与变化。先确定实际音节、序列 / word 槽与推进方式，再编写音乐音符；任意歌词的文字输入不能自动变成该语言的演唱。
4. 复音连奏按声部连接、音符重叠与踏板控制关系组织。踏板参与智能声部处理，不能直接复制钢琴延音数据。数值映射与阈值按当前状态确认。
5. 动态层、音乐力度、表情与音节控制分开记录。手册没有提供完整 CC / keyswitch 数值表，先从当前保存状态和可读配置取得依据，避免沿用其他库的 CC1、CC11、CC58 或切换键。
6. 保留自然辅音和起音，按音节的 attack / offset、专用连奏与短音分别处理时序。谱面位置和实际触发位置保持可追溯，不能给全库套用单一提前量。

## 状态与交付

保存音节 preset、CONNECT / MORPH、每字段参数、声部分配、连奏 / 释放、动态和麦克风状态。音节 preset、NKI 文件名与完整 Kontakt 组件各有不同范围；工程接入使用实际已保存的状态或已验证适配器。

按任务提供工程、MIDI、音频或谱面，准确说明映射和状态实现的范围。运行、界面和 Computer Use 继承主 skill 及会话授权；编写子技能使用文件与手册，不启动音源。

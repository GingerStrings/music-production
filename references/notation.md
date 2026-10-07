# LilyPond 原生写谱与改谱

创作或修改乐谱时，默认直接编写 `.ly` / `.ily`，用 LilyPond 编译所需 PDF。源码保存音符、声部、记号与排版决定，通常无需另建记谱 JSON。运行 LilyPond 无需启动 Cubase、Kontakt 或音频插件。

## 写谱与组织源码

- 单份短谱可放在一个 `.ly` 文件；合奏总谱与分谱可用音乐变量和 `\include` 共享 `.ily`。只维护一份音乐内容，各入口控制编制、移调、布局和分页。
- 直接按音乐需要使用原生语法，例如 `\tuplet` 连音组、`\grace` / `\acciaccatura` 装饰音、独立 `Voice`、`\change Staff` 跨谱表以及 `\transpose`。遇到不熟悉的写法，查所用 LilyPond 版本的官方手册并编译确认。
- 音高拼写、谱表与节奏声部归属由音乐意图决定。钢琴双谱表可用 `PianoStaff`，强弱可放在共享 `Dynamics` 中。左右手分工和独立节奏应明确表达。
- 改谱直接修改对应音符、音乐变量或排版指令，保留用户原版并保存新版本。总谱和分谱复用音乐内容时，同步重编译受影响的入口。

[../examples/native-score.ly](../examples/native-score.ly) 是独立可编译的原创钢琴短谱例，包含三连音、五连音、装饰音与同谱表独立声部。它演示写法，各项音乐选择仅适用于该谱例。

## 编译与交付

定位本机 LilyPond，记录实际版本。先创建输出目录，再直接运行：

```bash
mkdir work
lilypond -dno-point-and-click -o work/native-score examples/native-score.ly
```

`-o` 指定输出前缀；一般得到 `work/native-score.pdf`。多份总分谱入口分别编译。交付 `.ly`、所需 `.ily` 和 PDF，包含重编译所需的本地依赖；作者未知时省略署名，中文文本使用 UTF-8 并检查字体。

Windows 便携版宜放在 ASCII 路径并用绝对路径执行。若中文工作路径影响编译，将源文件及其相对引用一同放入 ASCII 临时目录运行，再把产物复制到交付目录；只暂存文件即可。保持源码内引用可移植，公开示例不写用户机器路径。

常规改写重新编译，处理编译错误和与本次改动有关的警告，检查受影响的谱面与分页。新谱查看最终 PDF 页面，关注节拍、声部对齐、弧线、文本碰撞及分谱翻页。普通源文件修改不需要先转 JSON，也不默认运行逐音 MIDI 回读或转换器测试。

如任务需要参考 MIDI，可在 LilyPond 源码加入 `\midi`。该输出用于谱面试听或核对，实际 Cubase 音源的奏法、CC 和延迟仍按工程任务处理。

## 接入已有音乐或 Cubase 工程

从演奏数据排谱时，确认音符真正的音乐位置、拼写和时值。名为 `score_duration` 的字段也可能保存短奏收音；补偿后的起点、采样重叠、keyswitch 和 CC 点不能直接当作印刷记号。需要整理音值时，结合源音乐保留有意的编辑说明。

同时交付 CPR 时，保留可追溯的声部和音符对应，分别处理记谱位置与音源事件时间。仅写谱的任务无需先创建工程。附带工具没有实现任意 `.ly` 与 CPR 互转，参考 MIDI 也不会自动配置音源。

## 何时使用可选 JSON 排谱器

已有适合其 schema 的结构化音乐数据，或需要重复批量生成时，可以使用 [notation-json.md](notation-json.md) 中的 `scripts/engrave.py`。其 v1/v2 接口与示例继续保留；只有选择该路径时才加载格式说明及配套核对流程。

转换器缺少所需记号时，通常直接编辑原生源码。只有任务明确需要可重复的数据转换时，才扩展转换器。修改生成的 `.ly` / `.ily` 后将它们作为该版本的编辑来源，后续不要重新运行生成器覆盖手工改动。`verify_engraving.py` 只检查配套生成器产物；原生谱面按编译和实际内容核对。

## 官方参考

- [文本输入与共享总分谱](https://lilypond.org/text-input.html)
- [命令行运行](https://lilypond.org/doc/v2.26/Documentation/usage/running-lilypond)
- [音高拼写](https://lilypond.org/doc/v2.26/Documentation/notation/writing-pitches)
- [节奏与连音组](https://lilypond.org/doc/v2.26/Documentation/notation/writing-rhythms)
- [多声部](https://lilypond.org/doc/v2.26/Documentation/notation/multiple-voices)
- [键盘谱与跨谱表](https://lilypond.org/doc/v2.26/Documentation/notation/common-notation-for-keyboards)
- [钢琴记号](https://lilypond.org/doc/v2.26/Documentation/notation/piano)

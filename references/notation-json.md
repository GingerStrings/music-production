# 可选 JSON 排谱器

本页仅用于选择 `scripts/engrave.py` 的任务，例如已有符合 schema 的结构化数据或重复批量排谱。创作和普通改谱默认使用 [原生 LilyPond 流程](notation.md)。下述字段与限制属于可选转换器接口，LilyPond 原生源码可直接表达更多记谱方式。

## 输入与记谱决定

从原始作曲数据优先读取真实音乐位置。MIDI 中通常缺少可靠的等音拼写、声部归属和弧线；经过延迟补偿的演奏 MIDI 也缺少原谱面坐标。先补全这些决定，不能把 MIDI 导入等同于完成记谱。

一个名为 `score_duration` 的字段也可能只是演奏门限。确认字段生产者；例如 0.425 拍可能来自短奏收音。结合实际音型决定如何记谱，保留原时值、记谱时值和原因。真实休止、换奏法准备、弱起与变速不能在整理时被隐藏。`engrave.py` 遇到不支持的时间会拒绝输入；需要原生节奏记法时可直接编写 LilyPond，避免迁就接口改动音乐。

动态、弓法、乐句连线和采样技法各自承担不同职责。不要把每个 CC 点变成强弱记号，也不要从采样连奏重叠直接生成弓法。谱面的音符 ID 应对应原始音乐，便于解释排谱产生的拆分和有意调整。

## 通用字段与 notation schema v1

根字段：`schema_version: 1`、`kind: "notation"`、`title`、`bars`、`parts`；可选 `subtitle`、`composer`、`font`、`provenance`。作者未知时省略，不能编造署名。`font` 为已安装字体名称，中文标题要实际检查字形。`provenance` 保存来源/编辑记录，不作为 LilyPond 代码执行。

`bars` 按音乐顺序列出所有小节。首小节必须有 `meter: [分子, 分母]`、`key: {step, alter, mode}`、`tempo`。后续省略的拍号、调号和速度继承前值。`tempo` 是整数四分音符 BPM；`key.mode` 为 `major` 或 `minor`；`step` 为大写 C–B，`alter` 为 -2 到 2。可选 `rehearsal` 排练编号与 `text` 表情/速度文字，仅在该小节起点输出。记谱器支持小节边界的变化；CPR 写入器仍有自己的适配限制。

`parts` 每项包含：

- `id`：安全且唯一的小写标识，决定文件名；`score`、`audit` 等内部文件名保留。
- `name`、`short_name`、`clef`：乐器名称与谱号。支持 treble、alto、tenor、bass 及文档源码列出的八度谱号。
- `notes`：按起点排序的音符/同节奏和弦事件。每声部当前为一个谱表、一条节奏流；声部内重叠被拒绝。空隙自动补休止。
- 可选 `breaks`、`page_breaks`：在指定的 1-based 小节之后给分谱换行/换页。它们不影响总谱或音乐事件。翻页点应结合演奏者实际空档检查。

每条音符包含 `id`、`beat`、`duration`、`pitches`。时间单位统一为四分音符，音乐从 0 开始，不含音源预备拍；支持精确分数字符串，例如 `"3/2"`。本接口支持二分音值网格至 1/16 个四分音符；非二分连音组可改用原生 LilyPond。每个 pitch 必须显式给出 `step`、`alter`、`octave`，其中 C4 = MIDI 60。和弦 pitches 共享起点和时值。

可选音符标记：`articulations` 数组（staccato、tenuto、accent、marcato），`dynamic`，`text`，布尔 `slur_start`/`slur_end`，`hairpin: "<"` 或 `">"`，布尔 `hairpin_stop`。标记须明确决定，弧线/渐变必须闭合。标记依附音符；当前接口尚无任意时刻的独立标记轨。

参见 [../examples/notation.json](../examples/notation.json) 的合成谱例。v1 输入和原有源码生成方式继续兼容。需要钢琴大谱表或同谱表多声部时使用下方 v2。

## notation schema v2：钢琴与多声部

根字段改为 `schema_version: 2`；标题、`bars`、音高和时间单位沿用 v1。每件乐器仍占一个 `parts` 项，分谱按乐器生成，钢琴两行保存在同一份分谱里。

v2 乐器字段为 `id`、`name`、`short_name`、`staves`，以及可选 `group`、`dynamics`、`pedal`、`breaks`、`page_breaks`。`group: "piano"` 需要恰好两个谱表，生成带大括号和贯通小节线的 `PianoStaff`；默认 `group: "staff"` 需要一个谱表，可与钢琴共同出现在合奏总谱中。

每个谱表包含唯一 `id`、`clef` 和 `voices` 数组。每个谱表支持 1–4 条独立节奏声部，每条包含唯一 `id`、`notes` 及可选 `voice_number: 1..4`。不同声部可以同时发声、同音重叠，并拥有不同的时值。声部内同节奏和弦继续用一个事件的 `pitches`；同一声部内的事件仍须按起点排列且不重叠。音符 ID 在所在声部内唯一，完整对应关系为 `part/staff/voice` 加音符 ID。

钢琴乐器项的最小结构如下，实际音符见 [../examples/piano.json](../examples/piano.json)：

```json
{
  "id": "piano", "name": "Piano", "short_name": "Pno.", "group": "piano",
  "staves": [
    {"id": "upper", "clef": "treble", "voices": [
      {"id": "melody", "notes": []},
      {"id": "inner", "notes": []}
    ]},
    {"id": "lower", "clef": "bass", "voices": [
      {"id": "accompaniment", "notes": []}
    ]}
  ],
  "dynamics": [{"beat": 0, "dynamic": "p"}],
  "pedal": [{"beat": 0, "action": "down"}, {"beat": 4, "action": "up"}]
}
```

单声部谱表默认由 LilyPond 决定符干方向；多声部默认按数组顺序使用 `voiceOne` 到 `voiceFour`。通常按最高、最低、次高、次低排列；奇数符干向上，偶数向下，内声部有自动横向避让。可用不重复的 `voice_number` 明确指定这些排版角色。谱表与声部归属需要由音乐意图决定，工具不按固定音高阈值猜左右手，也不从 MIDI 重叠猜内声部。各声部独立补休止并生成延音线。

`dynamics` 是乐器共用的时间轨，支持 `{beat, dynamic?, hairpin?, hairpin_stop?, text?}`。钢琴放在两行之间，单谱表乐器放在谱表下方。事件可出现在没有音符起音的位置；按唯一时间点升序排列，渐强/渐弱需由新的强弱或 `hairpin_stop: true` 闭合。音符上原有强弱仍可用于明确的声部差异，避免同时添加重复的共用记号。

`pedal` 是独立的延音踏板轨，置于最下方谱表下方。`action` 支持 `down`（踩下）、`up`（抬起）、`change`（同一时间先抬起再踩下）。时间点唯一且升序，初始为抬起状态，最后必须有 `up`；`change` 仅用于已踩下状态。抬起可在全曲结束点。曲尾抬起的打印线由 LilyPond 在终止小节线结束，MIDI 核对仍保留该时刻的 CC64=0。当前为全踏板记号，半踏、弱音踏板和选择延音踏板尚未提供接口。

```bash
python scripts/engrave.py examples/piano.json --out-dir work/piano-v1 --lilypond /actual/path/to/lilypond
python scripts/verify_engraving.py work/piano-v1 --report work/piano-check.json
```

v2 同样接受 1–64 件乐器。每件乐器的断行/换页选项用于其分谱。未知字段、混用两版乐器结构、无效声部编号、不可表示时值、声部内重叠和不闭合标记会报错。连音组、跨谱表、移调、鼓谱、TAB 与歌词等需求优先使用原生源码，本接口没有对应字段。MusicXML 导出未在本包实现。

## 生成和核对

下列生成、哈希与 MIDI 回读检查配套使用，适用于该转换器产物。直接编写或手工修改的原生谱面按 [原生流程](notation.md) 核对；不要把此处的转换检查设为每次改谱的前置条件。

先定位本机 LilyPond；版本和路径记录在私有任务资料。Windows 便携发行版宜放在 ASCII 路径，使用绝对路径执行。生成器在系统临时目录编译，然后在输出所在磁盘发布结果；避免依赖工作区中文路径的兼容情况。中文标题本身使用 UTF-8。

```bash
python scripts/engrave.py work/notation.json --out-dir work/engraved-v1 --lilypond /actual/path/to/lilypond
python scripts/verify_engraving.py work/engraved-v1 --report work/engraving-check.json
```

省略 `--lilypond` 时仅生成源码。生成器只使用 Python 标准库；回读脚本需要 `mido` 与 `pypdf`。源码声明 `2.24.3` 语法基线，本次运行兼容性以实际版本验证为准。所有目标目录/报告要求不存在，保留原始输入。

`music.ily` 共享各声部音符；`score.ly` 与每件乐器 `.ly` 分别生成总谱和分谱 PDF。编译警告视为需要修正的问题，失败不发布完成目录。`engraving-report.json` 保存文件哈希和逐音拆分对应。`audit.ly` 使用相同节奏/音高生成路径，去掉影响演奏长度的表情标记，编译 `audit.midi` 用于独立检查；该 MIDI 不替代 Cubase 演奏数据。v2 为每条逻辑声部建立独立、具名的核对轨，保留同音重叠，并在专用核对轨检查踏板 CC64 的时间和状态。核对 MIDI 中的声部分轨及踏板分轨用于检查，不表示目标 DAW 的轨道或路由。

回读脚本验证源码与数据对应、文件哈希、LilyPond 实际生成的每个音高/起点/时值以及 PDF 页存在。再渲染并查看每个最终 PDF 页面：谱号、临时升降号、拍数、声部对齐、弧线、休止、排练号、文本碰撞、页码和翻页。将视觉检查独立记录，不能将回读报告里的 `pdf_visually_reviewed` 自动改为真。

同时交付 CPR 时，分别核对记谱数据、延迟/奏法转换和工程回读；为有意的音值差异保留映射。该流程不声称音频转录准确、插件加载成功或已经试听。

## 官方参考

- [LilyPond 文本输入与共享总分谱](https://lilypond.org/text-input.html)
- [绝对音高和临时升降号](https://lilypond.org/doc/v2.26/Documentation/notation/writing-pitches)
- [LilyPond 命令行运行](https://lilypond.org/doc/v2.26/Documentation/usage/running-lilypond)
- [同谱表多声部及符干安排](https://lilypond.org/doc/v2.26/Documentation/notation/multiple-voices)
- [钢琴踏板记号](https://lilypond.org/doc/v2.26/Documentation/notation/piano)

本包提供原创转换工具，不包含 LilyPond 程序、用户作品或商业音源资料。

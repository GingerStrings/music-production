# 数据格式与工具

## 三类数据

1. `score.json`：创作已经确定的谱面位置、音符、明确的补偿值及 CC 事件。
2. `performance.json`：实际写入工程的事件时间。
3. `template-profile.json` / `validation.json`：输入指纹与静态验证结果。

音乐本身可使用任意生成方法或中间表示。下述 schema 服务于附带工具，不规定创作过程。

需要创作、改谱或打印谱时，默认直接编写 `.ly` / `.ily`，见 [原生记谱流程](notation.md)。已有结构化数据可选用 [JSON 排谱器](notation-json.md)；它的 `notation.json` 与下述演奏数据 schema 分开，不能直接传给演奏编译器。同时交付工程与谱面时，保留必要的来源对应。

## 谱面数据 schema v1

根字段：

| 字段 | 含义 |
| --- | --- |
| `schema_version` / `kind` | `1` / `"score"` |
| `title` | 作品标识，仅保存在中间数据中；当前写入器不改 CPR 的名称元数据 |
| `bpm` | 固定速度 |
| `meter` | `[分子, 分母]` |
| `preroll_beats` | 在音乐前添加的预备拍；每拍为四分音符 |
| `end_beats` | 输出总长度，包含预备拍和尾部；每拍为四分音符 |
| `tracks` | 乐器轨数组 |

每轨含 `template_index`、`notes`、`controllers`。索引从 1 开始，对应 `inspect` 返回的乐器轨顺序；不要通过猜测轨名来绑定音源。

每条 note：

| 字段 | 含义 |
| --- | --- |
| `beat` / `duration` | 音乐起点和时值，未加入预备拍 |
| `pitch` / `velocity` | MIDI 音高 0–127，力度 1–127 |
| `channel` | 可选，0–15，默认 0；即常见界面中的通道 1–16 |
| `advance_ms` | 必填，note-on 提前量，非负毫秒 |
| `release_advance_ms` | 可选，note-off 提前量，默认与 note-on 相同；负值表示推迟 |
| `timing_basis` | `documented` / `measured` / `estimated` / `none` |
| `evidence` | 前两种 basis 必填，说明来源或测量记录；内容由调用方核实 |

Keyswitch 可以以 note 编码；在自有更丰富的创作数据中保留其用途标记，再导出为当前 schema。工具不会根据音高自动猜测哪些音是技法开关。

每条 controller 含 `beat`、`controller`、`value`、`advance_ms`，可选 `channel`。CC 编号和值为 0–127。`beat` 可以为负，用于安排在音乐前的初始化；经过预备拍和提前量换算后仍须不早于工程零点。音符的 `beat` 必须非负。

CC 点是显式事件，工具不自动插值。若需要连续曲线，先按所用库和创作意图采样；若是离散技法命令，保持离散值。相同时刻的 CC 保持输入顺序，整体排序将同刻 CC 放在 note-on 前。需要严格先后触发的多个音符应使用不同的实际触发时间，避免依赖同刻 note 的隐含优先级。

谱面时值与演奏 gate 的换算见 [performance.md](performance.md)。脚本拒绝负触发时间、非正 gate、越界音符和未知字段；无法识别的创作元数据应留在其他文件中。

## 演奏数据 schema v1

根字段：`schema_version=1`、`kind="performance"`、`title`、`bpm`、`meter`、`end_beats`、`tracks`，可选 `timing_report`。

每轨有 `template_index` 与按时间排序的 `events`，事件仅有两种：

```json
{"type":"note","beat":2.4,"channel":0,"pitch":64,"velocity":82,"duration":0.8}
```

```json
{"type":"cc","beat":1.9,"channel":0,"controller":11,"value":72}
```

这里的 `beat` 已经是工程坐标，不再额外应用预备拍或延迟。可以直接生成 performance；调用方仍需保留谱面和补偿依据。不要把同一套补偿在这里和 Cubase 轨道偏移中重复应用。

## 命令

在仓库目录中运行，路径按实际情况替换：

```bash
python scripts/cubase_project.py inspect work/template.cpr --out work/template-profile.json
python scripts/cubase_project.py compile work/score.json --out work/performance.json
python scripts/cubase_project.py build work/template.cpr --profile work/template-profile.json --performance work/performance.json --out work/composition.cpr --report work/validation.json
```

`inspect` 不修改工程。它只对已支持的结构生成报告，包含轨名、插件 UID 和数据哈希；模板报告也应视为私有工作资料。

`compile` 只做显式的时间转换和 MIDI 范围验证；v1 使用固定 BPM，v2 使用速度图。它不测量延迟，不验证用户提供的 `evidence`，不决定艺术内容。

`build` 重新检查模板哈希，先在内存中写入、回读所有事件并核对乐器数据，再创建新 CPR。报告明确设置 `plugin_executed=false`、`runtime_tested=false`。工具错误返回非零状态；磁盘写入异常时可能留有不完整输出，检查报告与哈希后再使用。

已有输出不会覆盖。重跑时选新文件名或由用户明确管理旧结果，不给本脚本增加自动覆盖原工程的选项。

## 时间图与扩展事件 schema v2

根字段使用 `schema_version=2`，以 `tempo_map` 和 `meter_map` 替换 `bpm`、`meter`。其他必填字段沿用对应的 score/performance v1。两张图从零拍开始、位置严格递增；每个拍号变化位于前一个拍号的整小节边界。

```json
"tempo_map": [
  {"beat":0,"bpm":76,"curve":"step"},
  {"beat":32,"bpm":60,"curve":"linear"},
  {"beat":36,"bpm":48,"curve":"step"}
],
"meter_map": [
  {"beat":0,"numerator":2,"denominator":4},
  {"beat":2,"numerator":4,"denominator":4}
]
```

`curve` 描述**抵达该点的区间**：示例的 0–32 拍从 76 线性降到 60 BPM，32–36 拍保持 60，第 36 拍跳到 48。首点必须为 `step`。图中 beat 已包含预备拍，且不得超出 `end_beats`。

performance v2 每轨可带 `name`、`source_tracks`（原 SMF 的零基轨索引），根可带 `source_report`。note 可带 `release_velocity`（0–127，省略为 64）。v2 允许保存源文件中明确存在的零时值 note，并在导入报告中列出；score 编译仍拒绝非正演奏 gate。

新增的 performance 事件：

```json
{"type":"program","beat":0,"channel":0,"program":24}
{"type":"pitchbend","beat":4.5,"channel":0,"value":-2048}
```

program 为零基 0–127，弯音为 −8192…8191。原生弯音编码有独立宿主保存实例支持；非零 program 的字段解释主要依据 MIDI 语义与零程序宿主记录，运行验证范围较窄。配置专用插件音色时，可在映射版移除 GM program，同时在源数据保留它们，避免覆盖已保存的预置。

## 导入 MIDI

安装 `mido>=1.3,<2` 后运行：

```bash
python scripts/midi_import.py source.mid --title "Composition" --out work/source-performance.json
python scripts/midi_import.py source.mid --title "Composition" --groups work/groups.json --repair-overflow --repaired-midi work/repaired.mid --out work/source-performance.json
```

`groups.json` 是 `[{"name":"Piano","source_tracks":[1,2]}]` 形式的数组。提供 groups 时须覆盖全部非空源轨，不能重复索引。导入器保留源事件顺序、重叠同音 FIFO 配对、tempo/meter 和通道信息；多余 note-off、零时值音符及元数据进入报告。仅支持 PPQ 的 SMF 0/1；未实现的有声事件会拒绝。

只有明确使用 `--repair-overflow` 才会修复部分非法弯音 MSB。算法要求该通道有已知的初始整数半音 RPN 范围，以 2 倍递增范围并缩放该通道所有弯音。其他非法数据不修复。报告包含原始/修复哈希、范围变化和最大音高误差；原文件不覆盖。

同一轨只有一个 tick-zero MIDI-port 值时，导入器将其应用于该轨的全部初始事件，包括排在该元事件之前的 setup CC；该归一化写入报告。变化的 MIDI-port 不在当前范围内。`--repaired-midi` 仅修复弯音字节/RPN，保留源文件元事件排序。

新增乐器轨与配置音色的命令见 [cpr-scaffold.md](cpr-scaffold.md)。

## 进一步检查

通用脚本验证字节与事件的一致性。还应根据任务验证采样键位、奏法/CC 映射、状态重置、连奏规则、模板中的音量声像、路由和效果器。这些语义不能由一次成功的 CPR 写出自动得出。

需要 MIDI 备份时，从同一份 performance 生成标准 MIDI，再用独立读取器比较音符、控制器、通道与时间，避免把量化误差当成完全一致。谱面 MIDI 应来自谱面位置，保留两者不同的用途。

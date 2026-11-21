# music-production

**音乐创作与制作：从作曲编曲、虚拟歌声到音频、可编辑工程和乐谱。**

这是一个面向 AI 助手的音乐制作 skill，按任务使用音源演奏、SV 歌声、音频渲染与混音、Cubase 工程和 LilyPond 记谱模块。当前工程适配覆盖 Cubase CPR 与 Synthesizer V SVP；记谱默认直接编写 LilyPond 源码并编译 PDF。

旋律、和声、曲式、编制和情绪发展由每次创作决定。这里没有预设作曲套路，也没有“优秀作品必须满足”的艺术检查表。

## 适合什么任务

- “根据我的要求创作音乐，交付能继续编辑的 Cubase 工程。”
- “把已有音乐实现到我的音源模板中，处理实际的奏法和表情。”
- “使用指定的 SV 声库制作歌声，交付可编辑 SVP、人声与完整混音。”
- “按已有音源和工程数据渲染音频，完成混音并输出试听。”
- “不要操作界面，也不要运行插件，通过文件分析和写入完成工程，并说明验证范围。”
- “直接创作或修改 LilyPond 乐谱，交付总谱、分谱 PDF 与可编辑源码。”

skill 的入口是 [SKILL.md](SKILL.md)，按当前任务选择模块。文件处理、后台音频运行与界面操作的授权分别判断；SV 歌声录制和插件渲染沿用用户对软件执行与 Computer Use 的限制。

## 安装

将仓库目录命名为 `music-production`，放在 `~/.codex/skills/` 下。已配置 `CODEX_HOME` 的安装使用其下的 `skills/` 目录。保留 `scripts/`、`references/`、`subskills/` 和 `agents/` 的相对位置。各音色库的子技能位于 `subskills/`，由主入口按当前使用的库读取。

调用示例：

```text
请使用 $music-production，根据这次的音乐要求和我已有的音源创作，
交付原生 Cubase 工程，并落实实际需要的奏法、表情和延迟处理。
本次只允许文件处理，不运行 DAW 或插件。
```

也可以在支持 `SKILL.md` 的其他助手中使用。文件操作能力和终端执行能力由所用环境提供。

## Cubase 文件工具的范围

`scripts/cubase_project.py` 是适用于特定工程结构的**实验性模板适配器**。Python 3.10+，CPR 核心读写仅用标准库；MIDI 导入另需 `pip install -r requirements.txt`。

| 操作 | 当前实现 |
| --- | --- |
| 将显式音符/CC 与毫秒补偿换算为演奏事件 | 支持 |
| 检查兼容 CPR，生成模板指纹和轨道清单 | 支持 |
| 替换已有乐器轨的 MIDI，写入新 CPR | 支持观察过的 RIF2 模板结构 |
| 调整 MIDI 片段长度与左右定位点 | 支持 |
| 保留已有插件状态、路由与混音设置 | 写后比较乐器数据哈希 |
| 变速图、变拍、原生 14 位弯音 | schema v2 支持 |
| 按已有轨道骨架增轨、复制已保存的音源状态 | `cpr_scaffold.py`，须满足窄范围输入条件 |
| 标准 MIDI 导入、谱表分组、显式异常弯音修复 | `midi_import.py`，记录源指纹与转换误差 |
| 厂商新音色状态构造、宿主自动化写入 | 需要具体音源/结构适配 |
| 任意 Cubase 版本、任意 CPR 文件 | 尚无兼容保证 |
| 实际加载、声音与起音延迟实测 | 脚本不执行 |

已有轨编辑器要求每轨一个位于零点的 MIDI part、无非空宿主自动化且 MIDI 插入效果已旁通。schema v1 的固定 BPM/拍号需匹配模板；v2 可以重写速度和拍号图。轨道构建器可从一个已验证的骨架创建多条乐器轨并装入明确指定的本地插件状态。输入条件见 [轨道构建器](references/cpr-scaffold.md)。

适配范围限于已观察的 Cubase 15 工程结构。格式不匹配时，工具会在写出前报错。宿主加载和实际发声取决于目标环境及工程。

## Cubase 最小使用路径

准备自己有权使用的音源模板，仔细阅读 [数据与工具说明](references/data-and-tools.md)。以下命令中的 `work/` 存放私有工作数据，不提交到公开仓库。

```bash
python scripts/cubase_project.py inspect work/template.cpr --out work/template-profile.json
python scripts/cubase_project.py compile examples/score.json --out work/performance.json
python scripts/cubase_project.py build work/template.cpr --profile work/template-profile.json --performance work/performance.json --out work/composition.cpr --report work/validation.json
```

示例只是一个单轨的数据格式演示，包含**虚构的延迟估计**，没有指定真实音源的技法映射。实际创作须替换示例数据，匹配模板的轨道、速度、拍号和音源。`build` 要求列出每个模板乐器轨；静音轨可以使用空事件数组。

所有输出使用新文件名；已有文件不会被覆盖。`inspect` 生成的指纹只固定输入版本，不证明工程已经能在 DAW 中运行。

## 按制作任务选工具

基础 CPR 文件处理使用 Python 标准库。按需安装 MIDI 导入依赖 `requirements.txt`、Kontakt 静态检查依赖 `requirements-kontakt.txt` 或后台渲染依赖 `requirements-render.txt`。生成谱面 PDF 需要 LilyPond。使用者自行提供插件、声库和兼容模板。

- [音源子技能](SKILL.md#音源子技能)按产品和版本列出可选的演奏教程。
- [Kontakt 状态检查](references/kontakt-static.md)说明支持的输入、私人配置和音色名称识别范围。

- [Synthesizer V 歌声](references/synthesizer-v.md)：SVP、实际歌声录制、进程清理、同步对齐与工程合成。
- [音频渲染与混音](references/offline-render.md)：本地插件、信号路径、动态处理与音频交付。

- [演奏、奏法与延迟](references/performance.md)：工程实现中容易被误判的音源行为。
- [CPR 格式与适配边界](references/cpr-format.md)：结构、引用重定位、插件状态和扩展方法。
- [数据格式与命令](references/data-and-tools.md)：谱面/演奏时间坐标、JSON 和验证报告。
- [轨道构建与音源映射](references/cpr-scaffold.md)：克隆身份、插件状态来源、路由和验证边界。
- [LilyPond 原生记谱](references/notation.md)：直接写谱、改谱、共享总分谱源码与编译交付。
- [可选 JSON 排谱器](references/notation-json.md)：已有结构化数据的 schema v1/v2、批量生成和配套回读。
- [公开与维护](references/publishing.md)：不公开个人工程或商业音源状态的打包方法。

运行可重复的自动检查：

```bash
python -m unittest discover -s tests -v
```

测试包含跨变速时间补偿、非法事件拒绝、弯音范围修复、原生 MIDI 编解码、拍号/速度图、克隆身份和内部路由、引用重定位及伪引用回归。测试中的二进制块由代码合成，仅用于验证解析器行为。

### LilyPond 总谱与分谱

默认直接创作或编辑 `.ly` / `.ily`，再用 LilyPond 编译。下例先创建输出目录；Windows 使用便携版时的路径处理见 [原生记谱说明](references/notation.md)。

```bash
mkdir work
lilypond -dno-point-and-click -o work/native-score examples/native-score.ly
```

[examples/native-score.ly](examples/native-score.ly) 是原创钢琴短谱例，直接使用三连音、五连音、装饰音和独立声部。谱例只演示原生写法，曲式、风格和技法由实际作品决定。总谱与分谱可复用同一份音乐变量或 `.ily` 文件，无需经过 JSON 或 MIDI。

已有结构化数据且适合批量排谱时，可选择原有 `scripts/engrave.py`。v1 单谱表、v2 钢琴与多声部接口，以及 `examples/notation.json`、`examples/piano.json` 均保留；格式、依赖和核对方式见 [可选 JSON 排谱器](references/notation-json.md)。连音组、跨谱表等原生写法按谱面需要直接使用，JSON 接口缺少的功能无需逐项补齐。

CPR 适配器仍要求已观察过的模板结构。本包未实现任意 `.ly` / CPR 互转、音频扒谱或 MusicXML 导出；同时交付工程时需落实对应音源和演奏数据。

## 公开内容与许可

仓库包含原创说明、工具、数据示例和测试。使用者的路径、插件状态、素材与安装记录保存在自己的工作目录。使用时自行提供合法拥有的模板及音源。

本仓库的原创说明和工具采用 MIT 许可。商业音源和插件遵循各厂商许可。[许可证](LICENSE) · [CPR 公开研究来源](references/cpr-format.md#公开研究来源)

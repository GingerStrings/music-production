---
name: music-production
description: Compose and arrange music with artistic expression as the priority, produce Synthesizer V vocals, render and mix local instruments, and deliver editable Cubase CPR/SVP projects or LilyPond scores. Also supports native CPR inspection, instrument-state work, SV plugin-load recovery, audio previews, and notation. Audio transcription and arbitrary CPR-to-score conversion are not implemented.
---

# 音乐创作与制作

帮助 AI 完成音乐构思、编曲、音源演奏、虚拟歌声、音频渲染与混音，并按任务交付可编辑工程或乐谱。当前已有 Cubase CPR、Synthesizer V SVP 与 LilyPond 记谱的实现路径；旋律、和声、曲式、配器、节奏与审美取向由当前任务决定。

仅要求创作或修改谱面时，直接进入下方“生成总谱与分谱”，默认编写 LilyPond 原生 `.ly` / `.ily`，不要求先生成 JSON 或 Cubase 工程。工程与谱面同时交付时，保留可追溯的声部/音符对应关系，分别记录音源触发时间和记谱位置。

## 艺术优先与验证边界

- **音乐首先是一门艺术。** 以用户的表达意图与审美取向为中心，把主要时间和注意力用于作曲、编曲、演奏表达与音乐修改。工程技术服务于创作，不能主导音乐决定或挤占创作。
- **不得用工程验证方式验证音乐性。** 不编写“音乐性验证脚本”，不用单元测试、规则打分或统计阈值判定音乐是否自然、有张力、有表现力或动人。音符／CC 数量、曲线变化与差异、音域合法性、响度等数据只说明各自的数据或技术事实；它们不能证明艺术质量，也不能成为音乐性“通过／不通过”的依据。
- 艺术判断结合乐句、风格、上下文、作品意图和用户反馈展开。重复、留白、稳定动态、齐奏与不协和均保留创作空间；不要为了让指标达标或曲线显得丰富而改写音乐。
- 常规创作复用已有工具，随正常保存、编译或导出完成最低必要检查，默认不另写验证脚本、测试套件、逐事件核对表或审计报告。工具内置的格式与写盘检查正常执行，无需再做一套重复验证，也不充当音乐性证据。
- 只有开发或修改底层解析器／转换器、首次接入尚未确认的技术路径、遇到具体实现故障，或用户明确要求工程验证时，才对受影响部分做最小技术检查；达到当前实现所需的条件就结束，不扩展成整首作品的审计。

这些边界适用于全部引用文档和音源子技能。后文的核对、回读与验证仅服务于具体实现，不自动增加创作任务的检查步骤、报告或艺术验收指标。

## 按制作任务进入

| 当前任务 | 对应模块 |
| --- | --- |
| 作曲、编曲与音源演奏 | 结合用户音乐意图，按 [演奏与音源实现](references/performance.md) 落实声部、奏法和表情 |
| SV 歌声、SVP 与人声音频 | [Synthesizer V](references/synthesizer-v.md)，含指定声库、后台录音和同步对齐 |
| 音频渲染、混音与试听 | [音频渲染](references/offline-render.md)，按实际信号路径输出音频 |
| Cubase 原生工程 | [CPR 格式](references/cpr-format.md) 与 [轨道构建](references/cpr-scaffold.md) |
| 总谱、分谱与可编辑乐谱 | [LilyPond 记谱](references/notation.md) |

只读取当前任务需要的模块；输出格式与是否运行软件遵循用户要求。

## 音源子技能

下表列出可选的产品教程。按使用者指定的音源读取匹配的子技能，再按其中的实际库、版本和预置完成操作。每库有独立 SKILL.md 与控制参考；这些模块放在本 skill 的 subskills/ 内，由本入口按需读取，无需同时加载所有库。

| 目标音源 | 子技能 |
| --- | --- |
| Cinematic Studio Strings（CSS，合奏弦乐） | [css-performance](subskills/css-performance/SKILL.md)，区分 1.5 与 1.7 的控制方式 |
| Cinematic Studio Solo Strings（CSSS，独奏弦乐） | [csss-performance](subskills/csss-performance/SKILL.md) |
| Cinematic Studio Woodwinds（CSW，木管） | [csw-performance](subskills/csw-performance/SKILL.md) |
| Cinematic Studio Brass（CSB，铜管） | [csb-performance](subskills/csb-performance/SKILL.md) |
| Tokyo Scoring Strings（TSS，东京弦乐） | [tss-performance](subskills/tss-performance/SKILL.md)，当前依据为 Complete 2.0.0 |
| Native Instruments NOIRE（Pure / Felt 钢琴） | [noire-performance](subskills/noire-performance/SKILL.md) |
| Berlin Percussion - The Timpani（Kontakt / CAPSULE 定音鼓） | [berlin-timpani-performance](subskills/berlin-timpani-performance/SKILL.md) |
| Native Instruments Battery 4（鼓组 / 采样插件） | [battery-performance](subskills/battery-performance/SKILL.md)，含复制轨道后的宿主停用故障 |
| Strezov Sampling Árva Children Choir（Arva 童声合唱） | [arva-performance](subskills/arva-performance/SKILL.md)，含 divisi、True / Agile Legato 与 Syllabuilder 3 |

Kontakt 音色库的工程与状态操作见 [Kontakt 音色库共用操作](references/kontakt-library-workflow.md)；Battery 等独立插件按各自子技能接入。使用者可在自己的工作目录保存手册位置和预置记录。后续新增音源沿用独立子技能，并按需增加特定预置 / 脚本模式的参考，不扩大现有表格的适用范围。

## 前台界面与 Computer Use：默认禁止

除非用户明确要求或授权对应操作，本 skill 的所有流程默认遵守以下规则；引用文档、验证要求与子代理同样受约束。

- 不得打开、显示、激活或切换到任何前台界面，包括 Cubase、Kontakt、插件编辑器、独立宿主、播放器和谱面查看器。通过终端、脚本或文件关联打开界面也受此限制；已有窗口打开不构成操作授权。
- 不得使用 Computer Use / computeruse / CUA，包括 `mcp__cua_repl`、`cua` API、桌面截图、界面读取、鼠标键盘模拟及其他桌面 UI 自动化；不得改用其他工具或子代理绕过限制。
- “制作/修改工程”“导出试听”“验证可用”“完成全部检查”等任务要求均不自动授权前台界面或 Computer Use。两项权限分别判断：明确允许打开界面，仅放行所要求的界面动作；使用 Computer Use 仍须用户明确授权。已明确授权的操作在原有范围内继续有效，无需重复确认。
- 默认采用文件读写、终端、静态检查，以及任务已允许且不显示界面的后台渲染。后台插件执行权限单独判断；禁止前台界面不额外禁止已获授权的无界面渲染。
- 后台宿主、脚本和辅助进程须禁用 GUI / 插件编辑器；Windows 启动后台辅助进程使用隐藏窗口。隐藏启动参数不能保证插件不弹窗，启动前应确认所用路径支持无界面运行。路径需要可见窗口或交互弹窗时，停止该路径，不自动切换到前台或 Computer Use。
- 文件处理或渲染遇到阻塞时，继续完成其余已授权工作，并说明影响交付的限制。不得为附加检查擅自打开软件。

## 创作自由与任务边界

- 继承用户本次的艺术要求。用户未指定的创作选择保持开放，不把某首作品的结构、编制、风格或奏法写成所有作品的要求。
- 技术检查用于发现实现错误。不要以“合格作品必须如此”的方式规定段落数量、和弦进行、声部角色、高潮位置、情绪变化或必须使用的技法。
- 例子仅演示数据格式和技术操作。不要将示例音符、力度或控制器点当作作曲模板。
- 记谱优先使用 LilyPond 原生语法；连音组、装饰音、跨谱表等需求可直接写入源码，无需逐项扩展 JSON 转换器。CPR 工程适配器缺少所需结构时，再按工程任务扩展并验证，或说明缺少的条件。不要为了通过脚本而改变音乐意图。
- 读取用户已有工程、素材、音源信息和前文约束，再询问确实会阻碍实现的缺失信息。已经明确的偏好和授权继续有效。

## 确定 Cubase 实现条件

记录目标 Cubase 版本、输出位置、可用音源与已有模板，以及后台插件执行、前台界面和 Computer Use 各自的授权范围。前台界面和 Computer Use 默认禁止，仅按上方规则接受用户的明确授权；允许写文件或后台插件渲染不扩大这两项权限。

用户要求纯静态处理时，使用文件和终端工具；不要启动 Cubase/Kontakt、后台宿主或插件 DLL。用户要求音频制作或试听且会话允许插件执行时，可使用下方离线渲染流程。现有授权继续有效，禁止界面自动化与禁止后台插件运行分别判断。

复用已有私有音源记录；只有新用、变更或未知的信息需要补充乐器/预置、插件标识、库与脚本版本、可发声键位、奏法选择、CC 语义、延迟依据及所需本地文件。只检查相关位置，遵守用户排除的磁盘或目录，不为每首作品重建音源验证档案。公开仓库仅存规则和不含个人数据的示例。

区分插件已安装、保存状态可读取、采样盘当前在线和实际发声验证。用户说明采样盘离线时，保留原音色和路径，标明需要重新连接的依赖。

音源实现见 [references/performance.md](references/performance.md)。首次接触 CPR 适配器时读 [references/cpr-format.md](references/cpr-format.md)。

识别已有 CPR 中的 Kontakt 音色、处理未命名轨道或静态读取保存的乐器名称时，先读 [references/kontakt-static.md](references/kontakt-static.md)，使用 `scripts/inspect_kontakt.py`。它提取轨道组件状态、验证引擎指纹、还原 NIS/FastLZ 数据并交叉核对 NKI 名称，无需启动插件或使用界面。外层没有可读字符串时继续按此入口检查；仅凭轨名或旋律形态不能确认乐器。保存状态的身份与活动槽位、样本在线、实际发声分别报告。

涉及吉他演奏时，同时读演奏页的“吉他演奏实现”：结合原谱弦位与实际起音、力度、释放及音源模式落实演奏。说明实际写入的演奏处理及影响使用的限制，不把音源映射或音符回读当作音乐表现力的证明。

## 把音乐构思转换为演奏数据

保存两套时间信息：谱面上的音乐位置，以及插件实际接收事件的位置。两者之间的差异应可追溯到延迟补偿、奏法触发或明确的演奏决定。

- 音符：记录音高、力度、起点、时值和 MIDI 通道。需要连奏时检查所用预置的连接条件、重叠和同音重复行为；需要拨弦等奏法时验证真实的切换方式。
- **Keyswitch 与控制音必须便于用户手动编辑。** 所有音源的奏法开关、选槽、模式切换等控制音，默认保留在钢琴卷帘中容易选中、拖动和调整的适量时值；在不干扰当前发声及后续音符、切换和同键重触发的范围内可以写长一些。不要默认写成几毫秒或一两 tick 的细线。切换提前量与按键时值分别安排，具体规则见 [控制音的可编辑时值](references/performance.md#keyswitch-与控制音的可编辑时值)；各乐器子技能共同遵循。
- 控制器：依据具体库区分动态、表情、奏法选择和开关，按乐句意图实际写入必要的 CC 点。沿用已确认的映射和状态组织；出现漏触发、覆盖或切换异常时，再检查相关时刻的有效状态。不要只在说明里说“已做表情”。
- 延迟：分别考虑起音、连奏过渡、短音和控制器生效时间；保留足够预备拍。不能将不同的提前事件全部钳制到零点。
- 证据：区分手册/静态数据支持、估计和音频实测。仅通过文件分析时，不能报告已试听或已测出真实起音。
- 若已有轨道偏移、MIDI 插件或宿主自动化，检查是否会叠加补偿或覆盖新写入的控制器。

涉及管弦乐创作、续写或表情修订时，先读 [references/orchestral-cc.md](references/orchestral-cc.md)：按实际预置确认控制映射，以乐句和声部关系安排表达，再落实到音符、奏法和 CC。该页区分各乐器的处理及按需技术排查，不要求每次创作回读全曲或出具表达验证报告；有意的稳定长音、齐奏和共同渐强保留创作空间。

数据格式与命令见 [references/data-and-tools.md](references/data-and-tools.md)。附带脚本只执行已明确的数据和时间转换，不生成旋律，也不决定表达走向。可使用自己的中间表示，保持音乐位置与触发位置的含义明确；转换逻辑改变或出现具体转换错误时，再检查受影响的对应关系。

## 写入原生 CPR

优先从用户有权使用、已有正确音源和路由的 CPR 副本开始，使用兼容当前模板的适配器。只有新增或修改格式适配、遇到具体读取错误时，才针对受影响结构排查；不把额外的格式审计当作每次创作的前置流程。

附带适配器支持观察过的 RIF2 结构：`scripts/cubase_project.py` 编辑已有乐器轨，每轨一个从零开始的 MIDI part。schema v2 支持变速图、拍号图、音符、CC、program change 和 14 位弯音，调整片段长度和秒制定位点，并保留乐器状态与路由。schema v1 继续支持与模板一致的固定速度和拍号。

需要新增轨道或配置已有音色时，使用 `scripts/cpr_scaffold.py` 从经过验证的轨道结构克隆，并从明确指定的已保存工程复制插件状态。使用前读 [references/cpr-scaffold.md](references/cpr-scaffold.md)。它会重建轨道目录、根引用和实例标识；插件状态文件的构造仍由具体音源适配负责。

已有 MIDI 可用 `scripts/midi_import.py` 导入 schema v2，保留来源轨道、通道、端口和时间图。合并谱表、拆分多音色声部及音源键位转换应保留映射记录。遇到非法弯音数据，先诊断原始字节；显式扩大弯音范围并等比例缩放时记录误差，同时配置音源响应范围，不直接裁切数据。

更多轨道类型、SysEx、Note Expression 或宿主自动化仍需扩展并验证。不要套用其他机器的固定绝对偏移，也不要用改扩展名的方式交付 CPR。

原工程作为只读输入，输出写入新文件。复用写入工具内置的格式与保存检查，不另写逐事件核对脚本。保留实际使用的生成脚本与所需乐曲数据，便于继续编辑；工具自动附带的运行报告无需再扩展成审计材料。

## 离线渲染音频与试听

用户要求音频或试听、且当前会话允许后台插件运行时，读取 [references/offline-render.md](references/offline-render.md)。可用独立宿主恢复本地音源/效果器状态，按最终工程的 MIDI、速度与混音数据生成全曲或片段，无需操作 Cubase 界面。禁止 Computer Use 的约束继续适用；已获授权的后台渲染无需重复确认。

该流程包含插件状态恢复、连续 MIDI 分块、前后级增益与自动化、缓存复用、同响度对照和音频回读。基础函数见 `scripts/offline_render.py`，运行依赖单列在 `requirements-render.txt`。工程提取与复杂路由仍需明确适配范围，不能据此宣称任意 CPR 都能直接导出。

遇到具体发声或表情问题时，检查受影响声部的音源响应。常规交付不追加全轨动态测试；音频数据检查只说明可观察的信号事实，听感由用户自行试听判断。

## Synthesizer V 歌声与 Cubase 合成

涉及 Synthesizer V、SVP 或实际虚拟歌声 WAV 时，读取 [references/synthesizer-v.md](references/synthesizer-v.md)。按用户指定的引擎与声库制作歌词、音素、旋律、换气和表达；保留可编辑 SVP，并将实际歌声音频接入 CPR。

插件加载失败时继续判断独立程序与声库是否正常。在支持该流程的 Windows 环境下，可用临时 Lua 脚本驱动独立程序播放，按进程录音，再将对齐的人声加入混音与原生音频轨。这属于实时录制，须如实标注；使用条件、版本边界、真正的子进程、恢复文件和设置还原见引用页。不得以合成器导唱或其他声库替代用户要求的歌声。

不要用 `playing` 状态、单个同步信号或电平变化代替歌声交付。取得实际歌声音频，移除临时同步信号，并交付完整成品；干声片段可供用户自行试听。此流程沿用前台界面和 Computer Use 的约束。

## 常规检查与交付

常规交付随正常保存、编译或导出做一轮最低必要检查，复用已有工具；通过后直接交付，不为增加验证证据反复检查：

- 交付完整：所需工程、音频和引用素材齐全，文件可读取。静态解析与实际宿主加载的证据范围如实区分。
- 音频交付完整：有实际音频，覆盖歌曲结尾及需要保留的尾音；处理读取失败、全静音、意外截断等明显数据问题。用户未指定时长时，按作品自然结束，不另设固定分钟数。

不额外计算、记录或比对 SHA256／文件哈希，不将逐音符、逐 CC、逐弯音、插件状态比对列为默认交付流程，不为常规创作新增验证程序或验证报告。已有工具内部的保护检查复用即可；出现具体错误或用户反馈问题时，只针对相关片段与实现排查，修复后确认受影响部分即可。所有检查结论仅限技术实现，不用于判定音乐性。

试听及听感判断由用户掌握。助手不替用户记录是否试听，不创建“听感审查完成／未完成／通过”等状态，也不把这些状态写进交付说明或报告。提供音频即可；用户反馈后再按反馈修改。

新增轨道或修改解析器涉及的类型声明、引用重定位等规则见 [references/cpr-scaffold.md](references/cpr-scaffold.md)。这些是实现对应功能时的约束，无需在每次交付时再做全量审计。

实际改动速度表时，遵循 [references/cpr-format.md](references/cpr-format.md) 中的类版本与属性布局；未改动的部分不追加检查任务。

提供原生 `.cpr`、可重建的创作/演奏数据和必要使用说明。MIDI、音频和谱面按当前任务交付。用户要求 CPR 时，保留原生工程目标；遇到格式阻塞要准确说明，不把其他格式当作完成。

交付说明只写实际产物、必要使用方法及影响使用的限制，不附加审查清单或替用户评价听感。

## 生成总谱与分谱

需要创作、改谱、打印谱或分谱时，读 [references/notation.md](references/notation.md)。默认直接编辑 `.ly` / `.ily`，由 LilyPond 编译 PDF；源码本身保存记谱决定。用户指定其他编辑器时遵从其选择。

用共享音乐变量或 `\include` 组织总谱与分谱，按音乐意图确定音高拼写、节奏声部、弧线、奏法和强弱。普通改谱直接修改源码；需要原生技法时查对应版本手册。不要因附带 JSON 接口缺少字段而限制谱面能力或先增加转换层。

从既有演奏数据排谱时，先确认音乐位置和时值的含义；补偿后的起点、采样连奏重叠、keyswitch 和 CC 点不能直接照搬到谱面。确有音乐编辑或同时交付 CPR 时，保留必要的来源对应和差异说明。

交付可编辑源码和所需 PDF。常规改写重新编译并检查受影响的谱面与分页；新谱检查最终页面。转换逻辑改变或来源核对存在疑点时，再补相应的数据检查。不要给每次原生改谱附加 JSON 往返、逐音 MIDI 回读或转换器回归测试。

已有结构化数据或批量生成任务可选择 `scripts/engrave.py`；其 schema v1/v2 和配套回读脚本见 [references/notation-json.md](references/notation-json.md)。这些工具的接口范围只约束该可选路径。原生谱例见 [examples/native-score.ly](examples/native-score.ly)。

维护或公开本 skill 时读 [references/publishing.md](references/publishing.md)。

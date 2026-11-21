# Synthesizer V 歌声、录音与工程对齐

根据作品指定的引擎和声库制作可编辑 SVP。需要交付人声 WAV 时，优先使用当前版本提供的导出方式。如果插件加载失败且独立程序可以合成歌声，可在满足下述条件的 Windows 环境中，实时录制独立程序的音频输出。交付时注明音频取得方式。

## 制作 SVP

- 以目标版本保存的工程作为格式参考，按实际结构处理时间单位、速度图和文件结尾。将旋律对应到歌词、音素、起点与时值，按乐句安排换气、连音、延音和释放。
- 从用户指定的声库取得数据库标识、版本和适用的发音语言。跨语言演唱时，确认该声库支持相应语言和音素集合。参考已有歌声工程时，将配置信息保存在项目工作目录。
- 从可编辑 SVP 创建捕获用副本，只保留要录的声部。实时播放时须单独静音伴奏，渲染选择开关未必影响播放。把同步参考轨放在工程零点，给歌声留足预备时间。交付主工程可保留采用相对路径的伴奏。

## 准备后台实时录制

进程回环适用于 Windows build 20348 或更新版本。目标程序需要能向 Windows 音频引擎输出，使用独占驱动或 ASIO 时应确认可否捕获。后台启动、脚本部署及软件执行遵守主入口的授权约定。后台 GUI 进程同样受该约定约束。[任务入口](../SKILL.md) · [Microsoft Application Loopback](https://learn.microsoft.com/en-us/samples/microsoft/windows-classic-samples/applicationloopbackaudio-sample/)

1. 选择可隔离运行并能加载目标 SVP 的安装，识别真正承载音频引擎的进程。记录该进程的 PID、创建时间、路径与父子关系。启动器可能把音频委托给子进程。
2. 如果需要临时更改应用的输出设备，先保存原设置，优先使用独立配置。设备名、采样率与通道按实际设备选择。还原时仅撤销本次改动，保留其他实例或用户并发做出的修改。
3. 为每次录制分配新的工程副本、ready 文件、音频输出和日志路径。配置临时 Lua 模板中的三个路径占位符，路径采用正斜线，并按 Lua 字符串语法处理引号。每个工作目录只服务于本次进程和工程。
4. 确认当前安装允许在启动扫描期间读取已载入的工程，并调用播放接口。官方接口区分扫描时调用的 `getClientInfo()` 和运行脚本时调用的 `main()`。模板依赖前者的时序，应先在目标版本确认。启动器由调用方提供。[SV 脚本入口](https://resource.dreamtonics.com/scripting/tutorial-A%20Minimal%20Example.html) · [SV PlaybackControl](https://resource.dreamtonics.com/scripting/PlaybackControl.html)

## 捕获工具

| 工具 | 用法 |
| --- | --- |
| [process_loopback.cpp](../scripts/sv/process_loopback.cpp) | 捕获指定 PID 及其子进程的音频，写入 48 kHz 双声道 FLOAT32 WAV 和一份捕获报告 |
| [startup_playback.lua.in](../scripts/sv/startup_playback.lua.in) | 在目标工程已载入且找到本轮 ready 文件时，消费标记并从工程零点播放 |
| [make_sync.py](../scripts/sv/make_sync.py) | 在静音预备段生成两段可区分的短扫频信号，写出参考 WAV 和标记位置 |
| [align_capture.py](../scripts/sv/align_capture.py) | 分别定位同步信号，检查两次测得的时间偏移，截取完整工程并清除指定预备段 |

使用 x64 MSVC 与 Windows SDK 10.0.20348 或更新版本。在仓库根目录的开发者命令提示符中编译到私有工作目录。

```bat
if not exist work mkdir work
cl /nologo /EHsc /std:c++17 /O2 scripts\sv\process_loopback.cpp /Fo:work\process_loopback.obj /Fe:work\process_loopback.exe ole32.lib mmdevapi.lib
```

在工程副本中放入同步参考音频前，先生成参考文件。以下命令使用脚本的默认标记，分别位于工程第 0.5 秒与第 1.5 秒，每个持续 60 毫秒。

```text
python scripts/sv/make_sync.py work/sync.wav
```

启动目标实例后，以 `process_loopback.exe PID OUTPUT.wav SECONDS READY.json` 调用录音器，传入实际音频进程的数字 PID 和包含启动等待、整首作品与尾音的捕获时长。Lua 模板只会在脚本扫描时尝试一次。录音器启动后写出 ready，模板检查工程路径并消费标记后才开始播放。扫描早于 ready 时，本轮不会播放。清理本轮临时文件，调整启动顺序，再用新文件重试。

按真实歌声长度和尾音设置对齐时长。例如，要输出包含预备段在内的 10 秒片段，可使用下面的命令。默认预备段的前 2.25 秒会被清零，应确认这段只有同步信号。

```text
python scripts/sv/align_capture.py work/capture.wav work/sync.wav work/vocals.wav --marker 0.5:0.06 --marker 1.5:0.06 --duration 10 --clear-before 2.25
```

两个 WAV 需要采用相同采样率。若使用自定义标记位置或时长，要同时调整生成和对齐参数。录音等待超过默认搜索区间时，通过 `--search-seconds` 扩大标记搜索范围。

## 定位失败并交付

- 捕获无声时依次检查音频 PID、输出设备模式、ready 消费和播放记录。若参考轨有声而歌词区间静音，再检查声库、音素、轨道静音状态和合成进度。
- 两个同步信号求出的时间偏移应一致。出现偏差时检查丢包、重采样与漂移。捕获器按时间戳定位数据包，报告中可见间隙、重叠、无效时间戳和尾部补零。若缺包或补零覆盖预期歌声或尾音，应重录受影响的片段。
- 结束本次任务拥有的进程，核对 PID 与创建时间后再释放关联子进程。撤下本轮临时脚本和 ready 文件，恢复改动过的应用设置。若崩溃恢复阻塞启动，只处理可通过工程及进程身份确认属于本轮的恢复副本。
- 交付可编辑 SVP、移除同步信号的人声及所需混音。接入原生 CPR 时，使用与目标结构兼容的音频轨模板或适配器，写入 AudioEvent、音频池、采样格式、帧长与路由，并带齐工程引用的音频。录音已应用的轨道音量或声像应计入后续混音。

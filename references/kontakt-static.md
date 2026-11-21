# 静态识别 Kontakt 保存的音色

`scripts/inspect_kontakt.py` 从受支持的 RIF2 CPR 乐器轨或单独的 Kontakt 组件状态中读取已保存的 NKI 乐器名称。工具只读文件，可以在没有运行 Cubase 或 Kontakt 的环境中使用。

## 普通读取

用相对路径指定工程和新的报告目录。

```sh
python scripts/inspect_kontakt.py work/example.cpr --out work/kontakt-report
```

工具会解析 CPR 中的乐器轨和组件状态，从支持的 NIS 容器或未编码的 FastLZ 压缩块提取 NKI 引用，并用同一状态中的乐器名字段交叉核对。此路径只使用 Python 标准库。遇到需要额外输入的编码块，会在报告中标记为未识别，并保留同一状态中已经确认的名称。

对已提取的单个组件状态，可用 `--input-kind state`。自动模式将扩展名为 `.cpr` 的输入识别为工程，其他输入按组件状态处理。工程、单个组件状态和单个解压块的大小上限均为 128 MiB。

## 可选的编码状态读取

部分状态需要提供特定 Windows PE 引擎构建、匹配该构建且已验证的 profile，以及使用者自己安装的产品元数据。先安装 `requirements-kontakt.txt` 中的可选依赖。真实引擎、构建 profile 和产品元数据由使用者私下准备。

```sh
python -m pip install -r requirements-kontakt.txt
python scripts/inspect_kontakt.py work/example.cpr --config private/kontakt-static.json --out work/kontakt-report-full
```

配置 JSON 接受 `engine`、`profile` 和 `catalog` 三个路径字段。相对路径以该 JSON 所在目录为基准。也可在命令行分别指定 `--engine`、`--profile`、`--catalog`，对应参数优先。默认配置位置为技能目录下的 `private/kontakt-static.json`。一旦启用配置，三项都必须可用。

读取器会检查构建与其 profile 的指纹匹配情况。遇到引擎、表数据或元数据不匹配时，应保留错误信息，按实际安装情况核对输入。编码分支的兼容范围取决于具体构建和保存状态布局。

## 阅读结果

`report.md` 汇总每轨看到的乐器引用，`report.json` 记录来源、轨道、结构和名称匹配依据。独立组件状态没有原工程的轨道索引。退出码 0 表示所有检查目标均找到完整名称证据，2 表示部分或全部目标未识别，1 表示输入、配置或整体提取失败。

| 观察结果 | 解释 |
| --- | --- |
| NKI 引用与独立名称字段一致 | 可把这个名称归属于对应的保存状态 |
| 同一状态出现多个匹配名称 | 可列出多个引用，活动槽位和 MIDI 通道需要独立的路由证据 |
| 名称无法匹配或结构未识别 | 保留未解决项，轨名和音域只能作为线索 |

采样可用性、音源当前加载状态和实际发声需要另外确认。报告可能含工程路径、轨名、采样引用和文件指纹，应保存在私有工作目录。产品元数据值、派生表和解码后的插件状态仅在内存中处理。

配套测试用代码合成容器、压缩块、产品元数据和乐器字段。格式参考见 [ni-file 的 NIS 结构](https://github.com/Ma5onic/ni-file) 和 [FastLZ 格式实现](https://github.com/ariya/FastLZ/blob/master/fastlz.c)。

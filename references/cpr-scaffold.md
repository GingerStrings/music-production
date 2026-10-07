# 从已保存结构构建乐器工程

`scripts/cpr_scaffold.py` 是实验性的 RIF2 静态构建器。它适用于已有一个经过核验的乐器轨骨架，需要按明确映射复制为多轨的任务。每个输出乐器轨只有一个从零开始的 MIDI part，不运行 DAW、插件或音频宿主。

## 输入条件

- 模板首个顶层轨是 I/O 文件夹，包含 tempo/meter 和有效的输出设备；其下不含音乐轨。
- 第一个乐器轨含一个从零开始的 MIDI part、已观察到的 named attributes 和空宿主自动化。
- 模板输出通道结构只有首个 stereo 输出处于使用状态；目标总线 UID 由调用方核实，禁止猜测。
- 提供模板 SHA-256、每个插件状态的来源工程和 1 基乐器轨索引。提供来源 SHA-256 可防止选错修订。
- performance 必须为 schema v2，轨道 `template_index` 为 1…N，顺序对应映射数组。N 不超过 128，总事件不超过 200,000。

解析器先核验源 archive 的逐字节往返。陌生对象、丢失引用或插件状态不完整时会报错，不通过忽略这些错误继续输出。

## 映射文件

以下是字段示意，路径和哈希须替换为本次任务的实际值：

```json
{
  "template_sha256": "64-character-sha256-of-template",
  "output_bus_uid": 6,
  "instruments": [
    {
      "source_project": "work/saved-piano.cpr",
      "source_track": 1,
      "source_sha256": "64-character-sha256-of-donor",
      "gain_db": -12
    }
  ]
}
```

`component_file`、`controller_file` 可选，指向已有正确格式的插件状态字节。省略时整体复制来源插件的保存数据；更换组件时，调用方要核对它与插件 UID、控制器状态、MIDI 通道和输出结构的匹配关系。工具不将 NKI 文件自动转换成组件状态。

轨名优先取 performance 的 `name`，再取映射的 `name`。`gain_db` 当前只支持从实际保存值确认的 0、−6、−12、−15 dB，默认 −12；这些值是初始配置，尚未做混音。声像初始化为中央。

```bash
python scripts/cpr_scaffold.py work/template.cpr --performance work/performance.json --mapping work/instruments.json --out work/composition.cpr --report work/validation.json
```

输出必须是新的 CPR 和报告文件。模板、performance、映射、CPR、报告各自使用不同路径。

## 克隆与检查

构建器为每个克隆建立独立的对象身份、RuntimeID、内部总线及插件实例 ID；保留别名关系并修正内部总线引用。它重建顶层轨道数量、根 ID→对象引用表，重定位类/对象引用，清空骨架快控分配，旁通继承的 MIDI 插入及 EQ/strip，设置明确的输出路由。

克隆时只保留各 archive 类型的首个声明，其余实例引用该声明；已登记的基类声明不重复写入。命名属性及插件状态从类型和引用扫描中排除。输入与输出均检查声明唯一性，已有工程编辑器也会拒绝含重复声明的旧生成文件。

写盘前回读所有事件、轨名、插件 UID、组件/控制器哈希、速度缓存及每个速度点的属性表、拍号两处表示、part 长度、定位点及根引用表。速度对象按类版本校验至完整边界；v3 的点属性表数量必须与速度点数相同。报告明确标记 `plugin_executed=false` 和 `runtime_tested=false`。

曾有旧构建器输出通过事件回读后仍被宿主拒绝。测试数量和字节往返均不构成宿主加载证据；未经加载确认的修复版本应明确标为待确认。

模板中的 UI 布局、不透明非音乐元数据以及全局音频设备设置可能继续保留。组件中外部采样路径不会因磁盘离线被重写。采样存在性、授权、音源键位与动态语义、真实延迟、宿主加载和听感均由任务单独核验。

来源模板和组件是私有工作资料，不随公共 skill 发布。可再分发的测试只使用合成字段和事件。

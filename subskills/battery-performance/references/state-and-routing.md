# 状态、采样与输出

## 状态类型与来源

| 保存对象 | 实现时保留的关系 |
| --- | --- |
| Battery kit `.nbkt` | cell、采样层、映射与相关 kit 设置 |
| Cubase 保存的插件组件 / 控制器 | 当前插件格式、UID、外层封装和实例配置 |
| `.vstpreset` | 对应插件 UID、组件 / 控制器块与预置容器 |
| CPR 乐器轨 | 插件状态之外的 Active、MIDI 接入、音量、输出与实例身份 |

使用用户有权使用的已保存状态和匹配的适配器。`.nbkt` 按 Battery kit 格式读取；Kit 字节不能通过改扩展名、直接写入 audioComponent 或套用 Kontakt NKI 解码器来成为宿主状态。跨格式导入取决于当前 Battery 构建、目标宿主支持的状态封装和采样文件路径。

保留插件 UID 与实际加载格式的一致性，组件、控制器与音频输出布局一起考虑。某个来源允许空控制器块，不代表其他版本也允许。轨道名或已重命名的 Plugin Name 不足以证明插件身份；结合 IDString 的 UID、来源插件和可解析的状态判断。CPR 写入采用 [轨道构建](../../../references/cpr-scaffold.md) 中匹配当前项目的路径，并遵守主 skill 当前的数据与验证要求。

## 采样依赖与保存方式

保存 kit 时，Patch Only 保留对采样的引用；Patch and Samples 另存 kit 与采样；Monolith 将相应数据打包。依据交付目标和素材使用权限选择方式，不把 kit 文件本身视作采样已经齐全的证据。[官方 Save Kit As](https://docs.native-instruments.com/ni-tech-manuals/battery-manual/en/main-menu)

从保存的路径表读取实际 sample 引用，包括不同力度层、用户编辑后的采样和相关效果资源。迁移库位置时使用已确认的新根目录，保留映射记录；既有外接盘离线时沿用主 skill 的离线标记。不要因单个搜索结果为空便替换音色，也不要将商业采样或私有组件嵌入公共 skill。

破坏性编辑后的采样可能保存在另外的目录，需随当前状态确认这些引用。静态路径存在只能证明文件可访问，样本恢复和运行时兼容性还需要对应证据。[官方 Wave Editor 保存说明](https://docs.native-instruments.com/ni-tech-manuals/battery-manual/en/editor-page)

## 输出与后台渲染

Battery 默认将 cell 送到 Master St 1/2；需要分输出时，可通过 cell 的 Direct Out 分配，并在 Cubase 激活所需输出通道。读取当前状态后选择保留或改变路由；只收集 Master 时，送到其他直接输出的声音可能遗漏。[官方 Cubase 分输出说明](https://support.native-instruments.com/support/solutions/articles/69000879844-how-to-route-battery-cells-to-individual-outputs-in-cubase)

信号路径需要连接 cell / kit 路由、插件输出、宿主返回通道与最终输出。插件的 Active、输出总线启用和 mute / solo 分开处理；同一名称中的“启用”不足以互相替代。采用多输出模板时确认所需总线，不直接套用仅首个 stereo 输出的骨架限制。

允许后台渲染时，恢复实际组件和接收通道，按目标路由收集输出，并保留释放、镲片和效果尾音。采样循环、Beat / Sync 或同步效果依赖正确速度与宿主时间信息；渲染器未提供相应 BPM / transport 时，准确说明缺失，不能宣称与 Cubase 导出一致。运行授权与处理流程见 [离线渲染](../../../references/offline-render.md)。

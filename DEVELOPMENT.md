# 数字人分步开发与环境搭建

本项目先在 Windows 集显电脑上完成简化人物的离线生成与缓存回放，再接入外部 AI，最后在远端 GPU 环境验证 MetaHuman 与 Unreal。首次生成允许等待，第二次播放复用相同结果。首版固定镜头、单人物、半身、中文、720p / 24fps；画质和帧率随实测调整。

## 当前状态与完成目标

截至 2026 年 10 月 18 日：已完成最小环境、真实视频缓存、简化人物场景、Blender 离线生成器和模拟 TTS 嘴型链路；18 项自动测试覆盖缓存、生成与语音时间轴验证。已制作本地演示视频。尚无写实人物资产、外部 API 适配器和片段调度播放器。

本机已检测到 Core 7 240H、16GB 内存、Intel 集显、Python 3.11.9、FFmpeg 与 ffprobe。磁盘此前约有 408GiB 可用；内存此前仅约 743MiB 可用，启动开发前应重新检查并关闭不必要的程序。Blender 尚需安装或核实非标准目录安装。

首个里程碑是生成一段真正的人物视频，导入缓存后断网回放。完整初级版本再增加可配置嘴型、表情、头发、半身动作、外部语音与对话，以及片段选择和打断。缓存回放的流畅度不能作为首次 AI 响应速度。

## 步骤 0 固定工程约定

1. 使用当前仓库 `C:\Users\matth\digitalhuman`。每项开发从 main 创建独立 codex/ 分支；验证和提交后合并，遵守 AGENTS.md。
2. 在 .gitignore 加入 `.venv/`、`.env`、`work/`、`renders/`、本地工具路径配置及原始大资产目录，再生成这些文件。已有 `.cache/` 忽略规则继续使用。
3. 把角色、动作、贴图和渲染器版本纳入配置。大资产采用 Git LFS 或独立资产存储；不要直接提交缓存视频与 API 密钥。
4. 记录实际工具版本及 Windows 图形驱动版本；首版固定一个 Blender 补丁版本，不随意升级。

交付：干净工作区、版本记录、资产存储约定。此步骤只做工程整理，不安装 Unreal、CUDA 或本地模型。

## 步骤 1 搭建最小本地环境

### Python

保留当前 Python 3.11.9。PowerShell 中执行以下命令；它们是待执行步骤，本次制定方案不会自动安装软件：

```powershell
Set-Location C:\Users\matth\digitalhuman
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m unittest -v
.\.venv\Scripts\python.exe cache_pipeline.py status
```

不必激活虚拟环境，也不必修改 PowerShell 执行策略。现有缓存程序只有标准库依赖。接入 API 时再在此虚拟环境安装所选 SDK / HTTP 库，并锁定依赖；不要安装 PyTorch 或 CUDA。

### FFmpeg

已有 FFmpeg 和 ffprobe，先检查，无需重复安装：

```powershell
ffmpeg -version
ffprobe -version
ffmpeg -hide_banner -encoders
```

确认构建包含计划使用的 libx264 编码器和 AAC 编码器。找不到命令时，使用已有安装目录中的完整 exe 路径，或重新打开终端检查 PATH。

### Blender

建议选择 Blender 4.5 LTS 的 Windows x64 稳定补丁版作为本项目候选基线，从官方入口下载。采用该版本是为固定流程和插件兼容性，并非宣称它是当前最新版本。

安装后先启动空场景、保存工程、渲染单帧。首选 OpenGL 视口、简单材质；先用 Workbench 做管线检查，再用 EEVEE 检查材质。Cycles CPU 只用于短小对照，集显 GPU 渲染不作为前提。

示例命令中的路径必须替换为实际安装路径：

```powershell
& 'C:\Program Files\Blender Foundation\Blender 4.5\blender.exe' --version
```

交付：环境版本记录、成功渲染的单帧、6 项缓存测试通过。启动简单场景即崩溃或内存不足时先处理驱动和场景规模，仍失败则把渲染移到远端；本地缓存开发继续。

## 步骤 2 用真实视频验证现有缓存

准备自己拥有使用权的短 MP4，包含声音。没有人物视频时可先用普通测试视频，它仅验证缓存与播放器。

```powershell
.\.venv\Scripts\python.exe cache_pipeline.py import --video 'C:\Users\matth\Videos\sample.mp4'
.\.venv\Scripts\python.exe cache_pipeline.py status
.\.venv\Scripts\python.exe cache_pipeline.py play
```

修改 prototype.json 中的表情字段，再运行 status，应显示未命中；恢复配置后应命中。导入命令不会从配置合成内容，视频必须与配置人工对应。第二次播放前断网，确认仍可播放。

交付：一次导入、两次播放和配置失效记录。通过条件：声音正常、视频可解码、第二次不调用生成器、不依赖网络。现有单元测试使用的是不透明字节，不能替代这一步视频解码验证。

## 步骤 3 制作 Blender 最小人物场景

1. 使用有明确许可的低复杂度头部，或自行建立测试头部；暂不引入完整 MetaHuman。
2. 设置固定半身镜头、简单背景、一个主光及必要补光。初始贴图 1K，关闭细分、高密度发丝、布料和毛发物理。
3. 先制作 3 秒眨眼 / 转头测试，分别检查单帧与短序列；通过后扩展到 5—10 秒。720p / 24fps 为目标，困难时降到 640×360 / 24fps。
4. 将主资产保存为版本化 .blend 文件。记录骨架、Shape Key 名称、坐标系、单位、镜头与帧率。

交付：可重复渲染的场景和短片。此处检查人物能否稳定加载和变形，不验收最终真人相似度。

## 步骤 4 实现自动离线生成器

已新增 renderer.py、render_settings.py 和 renderer-command.json，并复用 tools/create_head_scene.py。运行入口见 README 的一条命令自动生成。

生成器读取 cache_pipeline.py 传入的配置快照，依次完成：读取资产 → 实际应用简化选项 → 加载音频和动画 → 分任务工作目录输出 PNG 序列 → FFmpeg 合成 MP4 → ffprobe 检查 → 成功返回。

Blender 使用后台模式调用，脚本通过 `--` 后的参数接收配置。场景加载、渲染引擎、输出路径和执行顺序由脚本固定。标准输出记录阶段、耗时与错误；非零退出禁止发布结果。用 argv 数组执行，不拼 shell 命令。

合成示例，假设图片从 1 开始且确为 24fps；实际生成器按配置填写帧率：

```powershell
ffmpeg -framerate 24 -start_number 1 -i 'work\job-001\frame_%06d.png' -i 'work\job-001\speech.wav' -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest -movflags +faststart 'work\job-001\video.mp4'
ffprobe -v error -show_entries stream=codec_type,codec_name,width,height,r_frame_rate -show_entries format=duration -of json 'work\job-001\video.mp4'
```

音频长度决定帧数并预留收尾；不要依靠 -shortest 掩盖缺帧或截断。首次调通后，再把真实生成命令数组写入 renderer-command.json：

```powershell
.\.venv\Scripts\python.exe cache_pipeline.py prepare --command-file renderer-command.json
.\.venv\Scripts\python.exe cache_pipeline.py prepare --command-file renderer-command.json
.\.venv\Scripts\python.exe cache_pipeline.py play
```

交付：第一次确实启动 Blender 并生成视频，第二次输出 CACHE HIT 且不启动 Blender。测试渲染失败、音轨缺失、错误帧率和配置不支持的情况。

## 步骤 5 单独跑通嘴型

初级模拟链路已实现：Windows SAPI 生成测试音频，测试音节编排事件，参数化嘴型 Shape Key 驱动 Blender。运行方法见 README。后续按下面流程替换真实 TTS / 对齐服务并提升口型，不将模拟事件当作真实音素对齐结果。

1. 先为测试头部制作中性及约 6—10 个嘴型，手动生成测试时间轴；检查闭唇、张口、圆唇等变形。
2. 接入外部 TTS，优先选择能提供中文音素 / viseme 时间信息的接口。只返回词或字时间戳时，不能直接当作精确口型，需额外对齐或面驱。
3. 没有可用时间信息时，增加外部音频面驱 / 对齐服务，统一为秒制时间戳及角色控制量；不得假设音频 API 天然提供面部曲线。
4. 使用音频时间轴把曲线烘焙到 Blender。边界插值、连续发音和句末闭嘴单独处理。

交付：同一头部的中文讲话短片，包含双唇音、圆唇音、停顿、数字和中英文混读。项目初始目标是抽检关键闭唇事件音画偏差不超过约 80ms；先记录实测，再调整门槛。

## 步骤 6 单独跑通表情与眼神

1. 增加中性、轻微微笑、疑惑、惊讶等少量可控表情，支持强度和进入 / 退出时间。
2. 将说话嘴型与情绪控制进行区域映射和限幅，测试微笑叠加讲话、眨眼叠加转头，避免嘴唇穿插。
3. 眼球、眼睑、眨眼与头部各自定义控制通道；AI 输出情绪意图，实际曲线由确定性规则生成。

交付：每种表情独立短片及两种组合短片。极值、切换、闭眼和静止倾听均无明显变形错误。

## 步骤 7 单独跑通头发与半身动作

1. 头发按 none、静态网格 / 发片、简化骨骼摆动逐级实现；首版不做发丝级物理。
2. 身体增加呼吸、点头、摇头、一个解释手势。动作有统一开始和结束姿态，标注是否可打断。
3. 为同一台词分别输出无头发、静态头发和简化动态头发，比较生成耗时、峰值内存和视觉差异。

交付：可切换头发选项的短片与半身动作片段。缓存整个最终画面，不能把独立预渲染嘴巴、毛发和身体直接拼接并期待正确阴影与遮挡。

## 步骤 8 建立外部 AI 适配层与分层缓存

先接 TTS，再接文本对话，最后接麦克风 ASR，逐个验证。选择服务时检查中文质量、接口可达性、输出格式、时间戳、限流、计费和模型版本；提供商确定后再锁定 SDK。环境变量由本机安全方式设置，日志和缓存不得包含密钥。

计划定义统一数据：原始输入、对话上下文版本、生成文本、模型参数、声音版本、音频文件及哈希、嘴型 / 面驱曲线、表情意图、动作计划、资产和生成器版本。

现有缓存只保存最终视频，需扩展分层缓存，避免改头发就重新付费合成相同声音：

- 音频缓存：精确文本、声音、语速、模型版本及生成参数。
- 面驱缓存：音频内容哈希、面驱模型版本、映射 / 绑定版本。
- 视频缓存：资产内容哈希或可靠 revision、音频与动画哈希、镜头、灯光、实际展开的质量参数、生成器版本。

对话响应缓存单独处理，纳入系统提示和上下文；不能仅凭同一句用户提问命中不同上下文的旧回答。API 返回的音频和曲线固定为本次任务快照后再生成，避免文本相同而内容不同。

交付：输入一句中文 → 外部生成声音和动画数据 → 离线生成视频 → 再次复用。超时、限流、余额不足、无效数据必须明确失败；仅对适合重试的请求有限重试，并控制重复计费。

## 步骤 9 实现模拟实时播放器

计划在基础流程稳定后新增本地 Python 服务和浏览器播放器，绑定 127.0.0.1；密钥只留后端。首版浏览器原生 video 元素即可，不强制安装 Node 或前端框架。

界面提供台词、表情、画质选项，生成、播放缓存、停止、强制重建按钮，以及生成中 / 缓存回放的明确状态。先做按钮触发，再接语音输入。

加入 idle、listening、thinking、speaking 状态片段。统一分辨率、帧率、镜头、曝光和姿态；提前加载下一段。先实现淡入淡出和短静止过渡，不把 HTML video 自动当作无缝切换保证。所有任务带响应编号；停止时取消待播放旧结果，迟到任务可存入缓存但不得自动播放。

交付：断网可播放已缓存片段；任意新台词先生成并显示等待状态。停止后声音和画面一起停，旧任务完成不会抢播。自由镜头和任意实时行为不在此阶段。

## 步骤 10 建立可设置的质量档位与验收

在生成器真正支持后提供三档：draft 为低复杂度角色、静态头发和简单材质；preview 增加皮肤细节与简化动态头发；final 使用远端 GPU 输出高质量角色。每一档保存展开后的具体参数和版本，而非只缓存档位名称。未知参数要报错，不得静默忽略。

固定同一台词和同一镜头建立对比集：嘴型、微笑、转头、眨眼、头发、半身动作各一段，再做组合片段。

验收分别记录：

- 首次生成：API、面驱、渲染、编码耗时及费用。
- 缓存回放：哈希校验、播放器启动、首帧时间和播放是否卡顿。初始目标 720p / 24fps 按原时长播放，首帧延迟实测后设定。
- 容错：缓存损坏、资产修改、进程中断、重复任务、配置变化和磁盘不足。
- 质量：至少 10 句中文测试，检查闭唇、口腔穿插、表情冲突、毛发穿插和片段跳变。

在增加并发生成前补充同键任务锁、发布替换失败回滚、恢复与缓存容量清理。当前版本是单用户串行工具，不提供并发和事务恢复保证。缓存需要预览、占用统计和显式清理；不要自动无限保留旧版本。

## 步骤 11 在远端引入 Unreal 与 MetaHuman

本地步骤 2—9 稳定后，再准备具有独显的 Windows GPU 工作站。使用 Epic Games Launcher 安装选定 UE 与匹配 MetaHuman 组件。UE 5.7 可作为候选，最终以实际插件兼容性验证锁定；不因版本更新自动升级项目。

如需编译 C++ 插件，按目标 UE 的官方说明补齐 Visual Studio 的 Game development with C++、MSVC 和 Windows SDK。检测到 VS Build Tools 安装不代表相关组件齐全。

1. 默认 MetaHuman 加载、单帧、短片与打包验证。
2. Blender 身体 / 服装与 MetaHuman 的受支持往返；面部 DNA 保留官方标定流程。
3. 将已有音频、表情和动作协议映射到 UE 控制器，替换离线生成器后端。
4. Movie Render Queue 输出序列，经相同编码与缓存接口返回本机。
5. 高写实离线效果通过后，再评估远端实时渲染与串流。

交付：同一台词在 Blender 简化后端和 Unreal 高质量后端均可生成、缓存和播放。两后端渲染缓存必须隔离，不能假设面部绑定和材质可以无损替换。

## 里程碑与工作量估算

按单人熟悉 Python、已有可用人物资产估算，以下为工作日而非承诺日期：

- M0：步骤 0—2，约 1—2 天，环境与真实视频缓存通过。
- M1：步骤 3—4，约 3—5 天，真正的简化人物自动生成并二次命中缓存。
- M2：步骤 5—7，约 5—10 天，嘴型、表情、头发和动作分别通过。
- M3：步骤 8—10，约 5—10 天，外部 API 与模拟实时播放器通过。
- M4：步骤 11，约 5—10 天做初步适配；精细形象、面部校准与真人感提升另估。

M0—M3 约 14—27 个工作日。没有人物资产、需要学习 Blender、API 无中文时间戳或需要自建面驱时应增加时间。每个阶段按出口验收后再进入下一步，不以首版达到真人级画质为前提。

## 官方资料

- [Blender 4.5 LTS](https://www.blender.org/download/releases/4-5/) 与 [硬件要求](https://www.blender.org/download/requirements/)。
- [FFmpeg 下载入口](https://ffmpeg.org/download.html)，Windows 可执行文件由该页面链接的构建方提供。
- [MetaHuman 硬件要求](https://dev.epicgames.com/documentation/metahuman/metahuman-hardware-requirements-in-unreal-engine)。
- [Unreal 的 Visual Studio 配置](https://dev.epicgames.com/documentation/en-us/unreal-engine/setting-up-visual-studio-development-environment-for-cplusplus-projects-in-unreal-engine)。
- [Unreal Movie Render Pipeline](https://dev.epicgames.com/documentation/unreal-engine/movie-render-pipeline-in-unreal-engine)。

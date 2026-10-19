# digitalhuman

初级目标：可设置简化程度，提前生成并缓存，第二次直接播放缓存，模拟实时数字人的观看效果。

环境搭建、各部位验证与后续集成步骤见 [分步开发计划](DEVELOPMENT.md)。

后续目标为缓存微控制模板、由 AI 提供意图、本地三维执行的原生数字人。联网、固定头肩、文字输入的单人开发路线、反例、阶段门槛与失败退路见 [微控制可行性与实现路径](docs/MICROCONTROL_FEASIBILITY.md)。该文区分当前视频原型与尚待验证的手机三维能力；质量先用缓存验收，全面性能优化后做。

本机已完成的环境安装、验证结果和启动命令见 [本机环境](ENVIRONMENT.md)。

## 简化人物场景

`tools/create_head_scene.py` 用 Blender 自带几何建立测试头部与半身，包含静态网格头发、简化眼部开合、轻微转头和呼吸。资产由脚本生成，无外部贴图或模型依赖。它是流程测试人物，尚非真人级角色；眼部开合采用几何缩放，嘴部支持简化 Shape Key 口型，无 TTS 输入时保持闭合，尚未实现真实眼睑与口腔解剖。

生成 720p 静帧及可编辑 .blend：

```powershell
.\.venv\Scripts\python.exe tools\blender.py --background --factory-startup --python tools\create_head_scene.py -- --output work\head-scene-v1\still --render still
```

生成 5 秒、24fps 动画序列；使用不同输出目录保存每次测试，避免旧帧混入：

```powershell
.\.venv\Scripts\python.exe tools\blender.py --background --factory-startup --python tools\create_head_scene.py -- --output work\head-scene-v1\animation --frames 120 --render animation
```

参数 `--width`、`--height`、`--frames` 控制输出规模，`--hair none` 关闭头发。场景使用 EEVEE、16 采样、固定镜头和简单材质，无细分与毛发物理；保存的 .blend 默认以低成本 Solid 视口打开。BodyControl 负责身体位移，HeadControl 负责头部旋转，EyeAperture 控制简化眨眼。

检查保存场景的转头、眨眼、呼吸、首尾姿态和头部镜头范围：

```powershell
.\.venv\Scripts\python.exe tools\blender.py --background work\head-scene-v1\animation\head-v1.blend --python tools\validate_head_scene.py -- --output work\head-scene-v1\animation\validation.json
```

校验脚本针对默认 720p、120 帧测试配置。渲染输出、报告与模型位于忽略的 work 目录，代码提交即可复现，不将生成图像或大资产提交到 Git。

合成为无对白 MP4：

```powershell
ffmpeg -framerate 24 -start_number 1 -i work\head-scene-v1\animation\frame_%04d.png -frames:v 120 -c:v libx264 -pix_fmt yuv420p -movflags +faststart work\head-scene-v1\animation\head-v1.mp4
```

当前已生成样片、保存工程并导入独立测试缓存，可再次播放：

```powershell
.\.venv\Scripts\python.exe cache_pipeline.py play --config work\head-scene-v1\animation\cache-config.json
```

该缓存配置是第三步验证的本地输出。新的自动生成流程使用下面的 configs/head-draft.json，不必手工导入视频。

## 当前实现边界

本仓库已实现 Python 标准库缓存管线、Blender 离线生成器和模拟 TTS 嘴型输入，支持完整渲染、编码、帧数 / 格式 / 音轨检查、解码后发布缓存。尚未接入 Unreal 或外部 AI API。运行时播放预渲染视频，不在本机实时渲染人物。

## 第五步模拟 TTS 与嘴型

```powershell
.\.venv\Scripts\python.exe tools\mock_tts.py
.\.venv\Scripts\python.exe cache_pipeline.py prepare --config work\mock-tts\render-config.json --command-file renderer-command.json
.\.venv\Scripts\python.exe cache_pipeline.py play --config work\mock-tts\render-config.json
```

第一条命令用 Windows 自带中文 SAPI 语音制作模拟 API 返回数据，无网络请求，不安装本地 AI 模型。测试文本由 fixtures/mock-tts-request.json 定义，默认“爸、妈，啊、诶、衣、哦、乌、飞。”。修改测试词时须同时提供 visemes 映射；这不是任意中文文本到音素的自动对齐器。

输出为 audio.wav、tts.json 和 render-config.json。tts.json 记录原文、音频路径与 SHA-256、真实音频时长、秒制口型事件、测试音节及停顿；每个事件包含 start、end、viseme、可选 strength。真实提供商以后转换成同样的 WAV 与事件格式即可接入。

嘴唇与口部自动创建 REST、MBP、A、E、I、O、U、FV 八种状态，并以 Shape Key 烘焙，下颌随开口权重运动；相邻事件平滑过渡，空白区间与结尾回到 REST。FV 仅是初级示意形状，没有真实牙齿接触；模型没有舌头、真实口腔或完整面部肌肉系统。

模拟时间戳按单独合成的音节编排，明确标为 synthetic-syllable-timing-not-forced-alignment，不能当作真实中文音素精度评估。缓存同时绑定音频和事件文件内容，改时间轴也会失效。

本次已生成的演示为 work/mock-tts/demo.mp4，可编辑工程为 work/mock-tts/demo.blend。测试结果与截图位于同目录的 shape-check、final-validation、integration-result.json。validate_lipsync.py 会重新加载 .blend 检查实际口部几何、口型权重、停顿与末帧闭嘴；该脚本针对默认测试语料，不适用于任意真实台词。demo 文件是本次测试的导出副本，重新生成后以新任务目录或缓存为准。

## 一条命令自动生成

```powershell
.\.venv\Scripts\python.exe cache_pipeline.py prepare --config configs\head-draft.json --command-file renderer-command.json
.\.venv\Scripts\python.exe cache_pipeline.py play --config configs\head-draft.json
```

第一次读取配置快照并调用 Blender → PNG 序列 → H.264 视频 → ffprobe 检查 → 完整解码 → 缓存。第二次同样的 prepare 输出 CACHE HIT，不启动 Blender。工作文件、可编辑场景和日志保留在 work/render-jobs 的独立任务目录。

实际可设置的参数：quality.width / height（偶数）、fps、samples、hair（none / static），performance.frames。初级生成器支持 draft / simple / bust、固定半身或 head-closeup 镜头及中性眨眼动作；不支持的选项报错。profiles preview / final、任意人物、复杂表情和外部 TTS 服务尚未实现。

预录音频可选：performance.audio_file 仅合成音画，不产生嘴型。需要嘴型时提供 performance.tts_file，且 text 必须与事件文件一致；系统自动采用其中音频。音频与事件时长不得超过 frames/fps，音轨尾部补静音。只有台词而无 TTS 事件文件会明确报错。

内置生成器自动把场景代码、生成器代码及本机工具路径、大小和修改时间纳入缓存签名；Python 源码统一换行后计算签名，Git 的 LF / CRLF 转换不会误触发重建。音频文件变化也会使缓存失效。生成前后检查配置快照一致性。该签名用于本机开发，外部模型与资产仍须自行版本管理。

生成失败不发布结果。当前仍是串行工具，不提供并发锁、磁盘配额或完整事务恢复；work/render-jobs 会保留中间帧，需要定期人工清理。

## 配置

编辑 `prototype.json`：角色版本、场景、镜头、质量、台词、声音版本、表情、动作及生成器版本全部参与缓存键计算。任何字段变化都会使旧缓存失效。

prototype.json 保留为通用缓存接口示例，不直接适配内置人物生成器。实际生成请编辑 configs/head-draft.json。后续再扩展 preview 与远端 final 档位。

角色、贴图、动作或外部模型发生变化时必须更新对应 revision；使用同一路径替换素材而不更新版本可能误命中。不要把 API 密钥写入配置、命令文件或缓存；由生成器从环境变量读取。

## 第一次：离线生成或导入

最简单的接入方式：从 Blender / Unreal / 外部服务得到包含同步声音的 MP4，然后导入：

```powershell
python cache_pipeline.py import --video "D:\renders\first-human.mp4"
python cache_pipeline.py status
```

也可使用命令文件调用生成器。已有 renderer-command.json 使用本项目 Python 和绝对项目路径：

```json
["{python}", "{project}/renderer.py", "--config", "{config}", "--output", "{output}"]
```

```powershell
.\.venv\Scripts\python.exe cache_pipeline.py prepare --config configs\head-draft.json --command-file renderer-command.json
```

生成器读取配置快照，等待离线渲染完成，在指定 output 路径写入 MP4；配置提供预录音频时才包含音轨。命中缓存时跳过生成器；显式加 --force 才替换，旧版本保留为 .previous-*。

首次渲染可以很慢；本机如果连场景都无法加载，仍需使用远端机器。离线不等于没有显存和内存门槛。

## 第二次：模拟实时观看

```powershell
python cache_pipeline.py play
```

缓存完整性校验通过后，Windows 默认视频播放器按视频原有时间轴播放。程序明确输出“缓存回放”；播放路径不调用 API，缺失或损坏时明确报错，不暗中生成。可用 `--dry-run` 仅检查路径。

目前是单片段回放，不支持实时转头、修改台词、无缝拼接或语义级打断。固定镜头下可验证外观、嘴型、表情和毛发的呈现；不能用回放速度推断真实 AI 响应延迟。动态回答必须先生成新视频再缓存。

## 原生桌面测试控制台

双击桌面或开始菜单中的“数字人测试控制台”，也可双击项目内的 `start_desktop.cmd`。使用现有 Python/Tk 环境，无需浏览器或网页服务。

控制台支持选择嘴型 / 半身场景、调整分辨率与帧率、采样数、动画帧数、头发与镜头，生成或复用缓存、强制重新生成、生成模拟 TTS、查看日志并运行自动测试。预览图显示首帧；点击“播放缓存”在独立 FFplay 原生窗口播放含声音的视频，空格暂停，“停止播放”关闭本控制台启动的预览。停止播放不会取消离线生成。生成任务在后台串行运行。

## 第 6—10 步桌面初版

- “表情 / 动作”：中性、微笑、疑惑、惊讶；强度、进入 / 退出时间、左右眼神；呼吸、静止、点头、摇头与单侧解释手势。嘴型与微笑分通道，闭唇及圆唇时限制微笑。
- 头发支持关闭、静态网格、简化整体摆动；不包含发丝物理。
- draft 展开为 640×360 / 24fps / 4 samples / 简单皮肤 / 静态头发；preview 为 960×540 / 24fps / 16 samples / 程序化微小凹凸 / 摆动头发。可继续覆盖可见参数，实际参数全部参与视频缓存。final 明确拒绝，等待远端后端。
- “AI / 验收”：输入台词后准备测试语音，再生成视频；选择 mock 可测试固定回复，选择 deepseek 可调用真实对话。也可点击“对话 → 生成并播放”完成整条链路。上下文保留在本次会话中，可清空。自动对话采用固定半身镜头，与缓存思考片段保持一致；手动准备台词使用当前选择的镜头。
- “生成四状态演示”预生成待机、倾听、思考、讲话，统一半身镜头与画质，以 120ms 黑场淡出 / 淡入过渡。它是预制状态演示，尚不是实时语音会话或无缝角色播放器。对话生成时可循环已有思考片段，完成后播放回复；停止使旧响应编号失效，后台任务可缓存但不抢播。
- 顶部“步骤验收”运行 10 句中文、4 种表情、3 种头发和 preview 组合渲染，输出 `work/acceptance/report.json`；“缓存管理”查看视频占用并由用户显式清理被替换的旧版本。有效缓存与音频、面驱分层缓存保留。

DeepSeek 采用官方 `https://api.deepseek.com/chat/completions`，模型输入框可修改；当前默认 `deepseek-flash`，具体以账号支持的模型为准。桌面密码框输入密钥后点击“设置会话密钥”，只保留在当前进程环境；也可在启动控制台前设置 `DEEPSEEK_API_KEY` 和可选 `DEEPSEEK_MODEL`。不要把密钥写入项目文件或发送到聊天。已缓存的对话可无密钥读取；首次外部请求必须有有效密钥。接口依据：[DeepSeek 官方调用示例](https://api-docs.deepseek.com/api_samples/chat_curl/)。

短回复请求显式使用非思考模式、1024 token 输出上限及普通文本模式，通过提示词要求 JSON，避免 JSON 模式偶发空正文。结构化回复按受支持的表情 / 动作枚举校验；纯文本回答使用本地固定的 neutral-with-blink / idle-v1，并标记行为来源。空回复、截断、损坏 JSON 仍明确报错，不执行模型生成的代码或命令，不自动重试计费请求。依据：[DeepSeek 官方参数说明](https://api-docs.deepseek.com/api/create-chat-completion/)、[JSON 模式空回复说明](https://api-docs.deepseek.com/guides/json_mode/)。任务输出分别保存于自己的工作目录，桌面只消费对应任务的结果，避免旧任务覆盖后抢播。

语音暂用 Windows SAPI，任意台词嘴型按音量窗口与测试元音序列近似，**不是中文音素对齐**；第五步的音节夹具仍可单独使用。DeepSeek 适配器只负责文本及行为意图。外部 TTS / 对齐与麦克风 ASR 尚待选择服务并实接，不能把本地替代测试标为外部 API 已验收。

音频、面驱、对话和状态片段分别缓存在 `.cache/layers`，视频在 `.cache/digitalhuman`。对话键包含完整上下文、系统提示、模型与参数；改变头发不会重新合成相同音频。缓存校验哈希；损坏后生成时重建，播放时拒绝。API 超时、限流、余额不足或错误输出明确失败，不自动重试付费请求。

同键生成通过进程锁拒绝重复执行。断电或强制终止后若留下 `.locks/<key>.lock`，确认记录的 PID 已退出后手动移除该锁再重试。发布替换失败会尝试恢复旧视频，已有缓存不会因正常生成失败被清空。渲染中断需重新生成，尚不支持从 PNG 断点续渲。技术检查不能代替写实质量、真实音画偏差与人工流畅度验收。

## 接下来需要接入

1. 外部 ASR / TTS / 对齐服务实接，记录模型和声音版本。真实 DeepSeek 对话已通过桌面按钮完成回复、SAPI 语音、160 帧视频生成与自动播放，并验证手动缓存重播和无密钥全层缓存复用；本机记录见 `work/acceptance/deepseek-live-desktop-validation.json`。模型别名升级后可通过启动环境中的 `DEEPSEEK_MODEL_REVISION` 更换对话缓存版本。
2. Unreal 高质量离线后端及更多角色、表情与材质选项。
3. 待机、倾听、回答片段播放器及过渡、取消机制。
4. 中文口型同步及实际画质验收；现有编码与解码检查继续保留。

## 验证

```powershell
python -m unittest -v
```

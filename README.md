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

本仓库已实现 Python 标准库缓存管线、Blender 离线生成器、DeepSeek 对话与动作计划适配、本地测试语音和五项独立控制，支持渲染、编码、帧数 / 格式 / 音轨检查及完整解码后发布缓存。尚未接入 Unreal 或外部 TTS / ASR。当前运行端播放预渲染视频，不在本机实时渲染人物。

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
- “五项控制”：闭眼、微笑、张嘴、点头各有0—1独立强度，注视可选看镜头、画面左右、上下；手动时长1—15秒。动作平滑进入退出，点头完成一次低头再抬头；眼睑覆盖眼球，避免通过压扁眼球闭眼。当前仍为简化技术人偶。
- 五项控制中的“AI 指令 → 生成并播放”将自然语言转换成动作时间轴，再生成无对白缓存视频。`deepseek` 使用“AI / 验收”中的模型和密钥；`mock` 仅输出固定的五动作演示，不理解任意指令。任务日志标明来源，右侧“五项控制计划”可查看实际执行的时间、强度和JSON。分辨率、采样、头发和镜头沿用“渲染”页。
- AI动作计划只接受闭眼 `eye_close`、注视 `gaze`、微笑 `smile`、张嘴 `mouth_open`、点头 `nod`；最多40事件、15秒，同一通道不重叠，拒绝未知字段、非法数字和任意命令。注视 `[x,y]` 的正数对应画面右/上。错误JSON明确失败，不自动重试或伪装成真实AI结果。
- 五项控制是独立的无对白测试入口；原有“对话 → 生成并播放”仍负责带语音的回答，尚未将任意五项时间轴与语音嘴型合并。已生成的视频可在“渲染”页选择“五项控制 / 最近结果”重播；停止阻止当前生成任务完成后自动抢播，但允许后台继续缓存。
- 头发支持关闭、静态网格、简化整体摆动；不包含发丝物理。
- draft 展开为 640×360 / 24fps / 4 samples / 简单皮肤 / 静态头发；preview 为 960×540 / 24fps / 16 samples / 程序化微小凹凸 / 摆动头发。可继续覆盖可见参数，实际参数全部参与视频缓存。final 明确拒绝，等待远端后端。
- “AI / 验收”：输入台词后准备测试语音，再生成视频；选择 mock 可测试固定回复，选择 deepseek 可调用真实对话。也可点击“对话 → 生成并播放”完成整条链路。上下文保留在本次会话中，可清空。自动对话采用固定半身镜头，与缓存思考片段保持一致；手动准备台词使用当前选择的镜头。
- “生成四状态演示”预生成待机、倾听、思考、讲话，统一半身镜头与画质，以 120ms 黑场淡出 / 淡入过渡。它是预制状态演示，尚不是实时语音会话或无缝角色播放器。对话生成时可循环已有思考片段，完成后播放回复；停止使旧响应编号失效，后台任务可缓存但不抢播。
- 顶部“步骤验收”运行 10 句中文、4 种表情、3 种头发和 preview 组合渲染，输出 `work/acceptance/report.json`；“缓存管理”查看视频占用并由用户显式清理被替换的旧版本。有效缓存与音频、面驱分层缓存保留。

DeepSeek 采用官方 `https://api.deepseek.com/chat/completions`，模型输入框可修改；当前默认 `deepseek-flash`，具体以账号支持的模型为准。在“AI / 验收”密码框输入密钥后点击“保存 / 更换”，由 Windows 凭据管理器安全保存在当前用户、本机，重启软件或电脑后自动读取；输入新密钥再次保存即可更换。若当前会话已有密钥，留空点击保存也可持久使用。密码框不回显已保存值，保存成功后清空输入；状态文字显示是否已保存。

“删除密钥”移除本软件保存的凭据和当前进程中的密钥，后续新任务立即停用它，不会删除已有视频或对话缓存。存储名称为 `DigitalHumanLab/DeepSeek/APIKey`；不写入项目文件、日志、命令行或缓存。启动时优先使用保存项，没有保存项则兼容启动环境中的 `DEEPSEEK_API_KEY`；如果另在 Windows 系统/用户环境变量设置过密钥，需在系统设置中另行删除，否则下次启动仍可能从该环境恢复。模型也可用 `DEEPSEEK_MODEL` 设置。已缓存的对话可无密钥读取；首次外部请求必须有有效密钥。[Windows 凭据持久性说明](https://learn.microsoft.com/en-us/windows/win32/api/wincred/ns-wincred-credentialw)、[DeepSeek 官方调用示例](https://api-docs.deepseek.com/api_samples/chat_curl/)。

密钥回归验证可运行 `.\.venv\Scripts\python.exe -m unittest test_credentials -v`，包含真实 Windows 凭据库的保存、替换、删除及独立新进程读取。测试只使用随机隔离的测试项和虚构密钥，结束后清理，不修改正式保存项或调用真实 API。

短回复请求显式使用非思考模式、1024 token 输出上限及普通文本模式，通过提示词要求 JSON，避免 JSON 模式偶发空正文。结构化回复按受支持的表情 / 动作枚举校验；纯文本回答使用本地固定的 neutral-with-blink / idle-v1，并标记行为来源。空回复、截断、损坏 JSON 仍明确报错，不执行模型生成的代码或命令，不自动重试计费请求。依据：[DeepSeek 官方参数说明](https://api-docs.deepseek.com/api/create-chat-completion/)、[JSON 模式空回复说明](https://api-docs.deepseek.com/guides/json_mode/)。任务输出分别保存于自己的工作目录，桌面只消费对应任务的结果，避免旧任务覆盖后抢播。

语音暂用 Windows SAPI，任意台词嘴型按音量窗口与测试元音序列近似，**不是中文音素对齐**；第五步的音节夹具仍可单独使用。DeepSeek 适配器只负责文本及行为意图。外部 TTS / 对齐与麦克风 ASR 尚待选择服务并实接，不能把本地替代测试标为外部 API 已验收。

音频、面驱、对话和状态片段分别缓存在 `.cache/layers`，视频在 `.cache/digitalhuman`。对话键包含完整上下文、系统提示、模型与参数；改变头发不会重新合成相同音频。缓存校验哈希；损坏后生成时重建，播放时拒绝。API 超时、限流、余额不足或错误输出明确失败，不自动重试付费请求。

五项动作计划缓存在 `.cache/layers/motion-plans`，动作事件、强度、注视、画质和生成器源码参与视频缓存；更改动作会生成新的结果。最新入口配置在 `work/micro`，每个桌面任务的实际计划、配置、结果与视频路径保存在自己的 `work/desktop/<任务ID>/response` 中。

可运行 `.\.venv\Scripts\python.exe tools/accept_micro_controls.py` 生成五个单项与固定组合样片，并验证重复请求跳过渲染、保存的 Blender 工程中的实际眼睑/眼神/嘴型/点头数据；报告在 `work/micro-acceptance/report.json` 和 `baked-checks.json`。该验收不调用真实API，不能代替真实DeepSeek动作联调或真人级画质评价。

真实 DeepSeek 五动作请求已由桌面按钮完成计划生成、121帧渲染与视频缓存；再次请求验证同时命中计划和视频缓存，不再调用API或渲染。该次证据及实际工程逐帧检查见 `work/micro-acceptance/deepseek-repeat/report.json` 和 `baked-checks.json`。

同键生成通过进程锁拒绝重复执行。断电或强制终止后若留下 `.locks/<key>.lock`，确认记录的 PID 已退出后手动移除该锁再重试。发布替换失败会尝试恢复旧视频，已有缓存不会因正常生成失败被清空。渲染中断需重新生成，尚不支持从 PNG 断点续渲。技术检查不能代替写实质量、真实音画偏差与人工流畅度验收。

## 写实静态头部基准

采用 [3D Scan Store 免费头部样本](https://www.3dscanstore.com/blog/Free-3D-Head-Model)。官方授权为个人使用，商用需另行联系厂商；模型、原始贴图和衍生工程仅保存在本机忽略目录，不随 Git 分发。原始样本没有头皮发型、面部骨骼或表情形变；本项目另建了短发与五项控制绑定，见下节。

完整原包在 `.cache/assets/3dscanstore/free-head.zip`，原始解压目录为同级 `original/`。下载校验记录在 `free-head.inventory.json`，含实际 URL、大小、SHA-256 和全部文件清单；ZIP 中每个文件通过 CRC 校验。原始 Blender 场景为 `original/Blender/Blender Scene.blend`，其默认设置是 GPU / 4096 采样 / 2800×1216 的眼部特写，不建议直接在本机启动最终渲染。

复现命令（解压命令只对空目标执行，避免覆盖原始资产）：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-assets.txt
.\.venv\Scripts\python.exe tools/download_free_head.py
.\.venv\Scripts\python.exe tools/extract_free_head.py
.\.venv\Scripts\python.exe static_head.py
```

`static_head.py` 另做最长边 2048 的 PNG 贴图副本，保留原始 JPG/TGA/置换贴图和原始工程。渲染使用 Cycles CPU、4 线程、64 采样、降噪、768×960，视口降低细分并使用实体模式；额外保留原厂镜头、材质和灯光的低负载兼容参考。生成正面及相机左右各45度的三张静帧、拼图、报告和内嵌预览贴图的 `head-preview.blend`。左右指相机在画面坐标中的位置，不是角色的解剖左右。原始面部材质与色彩空间保持不变。

最新结果路径由 `work/realistic-head/latest.json` 给出，内容缓存位于 `.cache/static-head/<hash>/`。源模型、JPG/HDRI 内容、渲染脚本、Blender 工具和参数参与缓存，第二次执行校验文件哈希后跳过贴图生成及 Blender 渲染。提高采样可用 `--samples 128`，提高贴图可用 `--texture-maximum 4096`，会建立新的缓存。静态基准不会替换已有技术人偶或清除旧视频缓存。

本机 Clash Verge 的当前订阅已添加资源域名的精确 `DIRECT` 规则；维护脚本为 `tools/configure_asset_direct.py`，仅操作当前订阅规则和运行配置，验证后通过本地管道热加载，不开启网络控制端口。原配置备份在 `work/local-config-backups/`，其中可能含订阅凭据，不应上传或提交。该脚本按本机配置目录设计，不应在其他电脑直接照搬。下载器使用官方同一 S3 桶的兼容域名，校验对象 ETag、字节区间、大小、完整 ZIP CRC 和最终 SHA-256，并支持保留分段继续下载。

本机验收记录位于 `work/realistic-head/acceptance.json`：完整原包 2,019,571,774 字节，原始资源哈希未变，三视角图片通过解码检查，内嵌18个图像资源的预览工程重新打开成功，第二次调用命中缓存；75项自动测试通过。静帧只是后续材质、灯光和动画改进的基准，不代表完整数字人的真人化已完成。

## 写实头部的短发与五项控制

桌面“五项控制”页可选择“写实扫描头部”或“技术人偶”。写实角色复用既有手动输入、受约束的 AI 时间轴、视频缓存、计划查看和原生播放流程；分辨率、帧率、采样和镜头仍取自“渲染”页。写实头发选择“静态头发”或“关闭头发”；“简化摆动”明确拒绝，目前短发只随骨骼运动，无发丝物理。该入口生成无对白视频，带语音的原有对话入口仍使用技术人偶，尚未将语音面驱迁移到扫描脸。

`ScanRig` 提供 `eye_close`、`gaze_x`、`gaze_y`、`smile`、`mouth_open`、`nod` 六个可编辑主控属性，分别对应五项动作，其中注视拆为两个轴。安全的简单表达式驱动形变和骨骼，关闭 Blender 自动运行 Python 时也可工作。动画逐帧写入主控属性并使用线性插值；可在 Blender 中编辑这些属性、形态键或骨骼。

- Root / Neck / Head / Jaw 骨骼与归一化皮肤权重共同完成点头、颈部过渡和下颌张嘴。根据网格路径区分几乎重合的上下唇，上唇不随下颌下拉；上下牙齿按网格岛分别绑定，舌头随下颌。
- 头部、睫毛和眼部湿润层共同响应闭眼；新版微笑拆为嘴角、面颊、眼睑联动与张嘴组合修正，细节见下方微笑变形样板。
- 眼球及角膜在各自的真实中心转动，锚点随 Head 骨骼运动；保持原始中性眼球位置。
- 发型为本地生成的深棕色短发：42,000 条原生 Hair Curves、每条8点，固定随机种子、渐细发梢、头皮 UV 锚点及 Head 骨骼跟随。头皮网格保留供编辑与锚定，不将光滑头皮壳当作发丝渲染。低采样视频会损失细发丝细节，三视角静帧使用更高采样供外观比较。

标记与发型参数在 `configs/scanned-head-landmarks.json`；该标记只适用于当前扫描拓扑，更换脸型/拓扑需要重新校准。构建结果与完整贴图保存在 `.cache/layers/scanned-rigs`，本机入口为 `work/scanned-head/rig.json`；原始资产及此前光头基准不变。角色、绑定、发型源码和参数、渲染源码、工具版本、动作与画质参与缓存。写实后端独立于技术人偶后端，原有视频不会被覆盖。

运行 `.\.venv\Scripts\python.exe tools/accept_scanned_head.py` 做实际验收：五个独立动作、组合动作、原有真实 DeepSeek 缓存计划经桌面任务后端驱动扫描脸，逐帧检查主控、闭眼遮挡、嘴唇分离、眼球中心和点头时发根贴合，完整编码/解码视频，并用禁止再次渲染/API调用的断言验证复用。该验收只复用项目中已验证的真实 AI 计划，不产生新的 API 计费；没有该缓存则明确失败。报告和视频入口在 `work/scanned-head/acceptance/report.json`，高采样短发三视角保存在 `.cache/layers/scanned-portraits`。

本机本轮验收：81项自动测试通过，7段实际视频共103帧逐帧检查通过，五项单动作、组合和真实 DeepSeek 缓存计划均验证二次调用不重新渲染。闭眼测试30条瞳孔区域射线全部被眼睑遮挡，张嘴唇间距由0.036厘米增至2.289厘米，点头时抽样发根距头皮最大约0.02厘米。原生控制台构造及桌面任务后端通过检查；本轮未执行操作系统级的自动鼠标点击。

这是可继续雕刻和调参的基础绑定与短发，不包含完整 FACS 表情库、动态皱纹、语音音素口型或发丝物理；这些仍需分别推进真人化质量验收。

### 微笑变形样板

“五项控制”页新增“微笑样板”按钮，自动选择写实扫描头部，沿用当前画质，执行6秒固定时间轴：轻笑 → 明显微笑 → 微笑与张嘴组合 → 组合中的闭眼 → 恢复中性。此入口不调用 AI，也不需要密钥。手动控制和 AI 的原有 `smile` 接口同样使用新绑定。点击“手动生成”仍可自行组合五项动作。

新版 `ScanRig` 的 `smile` 主控驱动四个可编辑形态键：

- `SmileCorners`：局部嘴角向外及向上牵引，保留中央唇缝。
- `SmileCheeks`：面颊抬升与适度前向饱满变化，避免直接改动唇缝和眼睑。
- `SmileLids`：轻微缩小眼裂，头部、睫毛和眼部湿润层使用同一变形场；由 `smile * (1-eye_close)` 控制，显式闭眼优先，防止重复闭合。这是一种固定友好微笑风格，不表示所有微笑都应眯眼。
- `SmileOpenCorrective`：由 `smile * mouth_open` 激活，减少张嘴组合时的嘴角横向拉伸，并适当修正上提。它不取代下颌骨骼或关闭中央唇缝。

这些形态键在骨骼蒙皮之前求值，可在 Blender 中继续雕刻；原始扫描资产不改写。它们是确定性的程序形变近似，不是肌肉物理模拟或已训练的神经面部模型，也不包含动态皱纹。新绑定与渲染源码参与缓存身份，旧视频保留，不能误命中旧的单一微笑形变。

运行 `.\.venv\Scripts\python.exe tools/accept_smile.py` 进行本机实际验收：检查嘴角、面颊和下眼睑的真实网格位移；对比启用/关闭组合修正后的嘴角宽度；检查12组微笑与张嘴参数、微笑完全闭眼的30条遮挡射线；通过桌面任务后端生成49帧视频并逐帧验证驱动，完整编码/解码后，在禁止重新渲染/API调用的条件下验证缓存复用。高采样静帧包括轻笑、满强度、组合、闭眼和侧面，并保留前版对照。本机验收依赖此前的扫描脸资产与旧版验收记录。入口为 `work/smile-sample/report.json`，参考图片缓存在 `.cache/layers/smile-review`。这些检查不是完整面部自碰撞或真人相似度证明，视觉结果仍需人工确认。

本轮85项自动测试通过；49帧视频、12组参数和缓存复用检查通过；9张512×640、32采样参考图已做视觉检查。满强度时左右嘴角各上提约5.3毫米、面颊约3.2毫米，下眼睑约0.4毫米；完全张嘴组合修正将每侧嘴角的横向拉伸减少约1.8毫米。原生窗口构造与实际桌面任务后端已验证，本轮未做操作系统级自动鼠标点击。

## Blender 实时预览

桌面控制台新增“实时”页。点击“打开实时窗口”后，扫描脸在独立的原生 Blender 窗口中加载一次；拖动微笑、张嘴、闭眼、注视左右/上下及点头姿态滑块，持续更新同一个角色，不需要先生成视频。“微笑演示”在该窗口连续执行现有6秒样板，结束后回到中性；“恢复中性”或拖动滑块可打断演示。此处点头值表示头颈俯仰姿态，离线点头事件仍具有原来的时间曲线。

也可直接运行 `.\.venv\Scripts\python.exe desktop_console.py --realtime` 打开实时页并自动加载预览。

使用步骤：

1. 启动 `desktop_console.py`，切换到“实时”页。
2. 保持默认“快速实体”及关闭短发，点击“打开实时窗口”。首次缺少绑定缓存时先构建资产，已有缓存则直接加载。
3. 等待“实时窗口已连接”，拖动滑块或点击“微笑演示”。可在 Blender 中旋转观察，但控制台会继续驱动绑定。
4. 需要皮肤与灯光预览时切换“实时材质”（EEVEE），等待首次着色器编译；短发可以单独打开。若反馈变慢，切回快速实体或关闭短发。
5. 点击“关闭”结束本控制台创建的 Blender 进程。关闭控制台也会关闭其拥有的实时窗口；其他 Blender 窗口不受影响。

快速实体使用原始颜色贴图、低细分和工作室照明，隐藏透明角膜/湿润层，主要检查几何与运动；EEVEE 使用1级视口细分及简化的发丝材质，不开启光线追踪。两种模式均不等于 Cycles 离线成片。预览修改只保留在内存中，不写回扫描资产，不改变已有离线渲染缓存。实时页当前支持手动控制及固定微笑演示，尚未接入实时AI指令流、语音或口型。

实现为 `realtime_preview.py` 管理独占子进程，`tools/realtime_viewport.py` 使用 Blender 主线程定时器应用最新状态。局部文件通信位于 `work/realtime/<session>/`，不监听网络端口，不读取API密钥。滑块合并短时间内的变化，并在客户端做短暂平滑过渡；不排队执行过时的滑块状态。窗口状态、实际形态键及骨骼值、近次视口绘制频率和GPU名称写入会话报告。控制台心跳中断45秒后，实时窗口自行退出。

Windows文件替换期间的短暂读锁不再停止实时定时器：心跳、命令和状态读取失败会在后续轮次重试；心跳/状态写入遇到共享冲突时跳过本次发布。心跳使用单调计时的45秒租约，只有读到变化的心跳值才续约，反复读取同一份旧文件不能阻止超时退出。实际故障回归会分别独占锁住心跳与状态文件各1.5秒，验证同一 Blender 进程保持运行并在解锁后继续响应；本轮93项自动测试通过。

运行 `.\.venv\Scripts\python.exe tools/accept_realtime.py` 做实际验收：启动可见原生 Blender 窗口，验证多次动作始终使用同一PID、实际形态键/骨骼/眼球数值、6秒微笑演示及恢复中性、实体/材质/短发切换和退出清理；确认没有创建离线视频渲染任务。按需使用 Blender GPU 视口快照检查图像，不使用FFmpeg或逐帧视频生成；报告在 `work/realtime-acceptance/report.json`。自动测试还覆盖非法强度、Windows读文件锁重试、加载期间取消、重复启动和桌面滑块分发。

本机 Intel 核显测试已实现交互预览，连续动作的视口绘制频率约10—13 FPS，不能视为稳定30 FPS或手机性能保证。统计来自视口绘制回调，不是GPU耗时分析；指令接收时间也不是从输入到显示器出图的完整延迟。实际速度受窗口大小、材质、短发和其他运行程序影响。下一步可根据测量结果继续优化模型和运行端。

## 接下来需要接入

1. 外部 ASR / TTS / 对齐服务实接，记录模型和声音版本。真实 DeepSeek 对话已通过桌面按钮完成回复、SAPI 语音、160 帧视频生成与自动播放，并验证手动缓存重播和无密钥全层缓存复用；本机记录见 `work/acceptance/deepseek-live-desktop-validation.json`。模型别名升级后可通过启动环境中的 `DEEPSEEK_MODEL_REVISION` 更换对话缓存版本。
2. Unreal 高质量离线后端及更多角色、表情与材质选项。
3. 待机、倾听、回答片段播放器及过渡、取消机制。
4. 中文口型同步及实际画质验收；现有编码与解码检查继续保留。

## 验证

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
```

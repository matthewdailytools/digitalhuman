# 本机最小开发环境

2026 年 10 月 18 日已完成安装与基础验证。

## 已就绪的工具

- Python 3.11.9，项目虚拟环境为 `.venv`，现有程序没有额外 pip 依赖。
- FFmpeg / ffprobe 9.0.2，已确认 libx264 与 AAC 编码器可用。
- Blender 4.5.14 LTS，官方便携版，安装在当前用户的 LocalAppData/Programs/Blender 下。压缩包 SHA-256 与官方校验文件匹配。
- 本机绝对路径记录在被 Git 忽略的 `local-tools.json`；未修改全局 PATH 或 PowerShell 执行策略。

## 已完成的验证

- 项目 6 项缓存单元测试通过。
- 生成并完整解码 2 秒、640×360、24fps、H.264 视频与 AAC 测试音；缓存导入、二次命中与播放路径解析通过。尚未人工听音或启动默认播放器。
- Blender Workbench 和 EEVEE 均成功保存 .blend 并渲染 640×360 PNG；已检查 EEVEE 图像。使用默认立方体，不能代表人物或毛发性能。
- Workbench 单帧日志约 1 秒，EEVEE 首次约 20 秒，包含初始化与着色器准备，不能作为连续帧率。

测试输出保存在被 Git 忽略的 `work/environment-smoke/`。

## 内存处理

对 Chrome、Edge、豆包、千问共 53 个进程进行一次 Windows 工作集回收，没有结束这些进程。该操作让可回收页面暂时移出物理工作集，不等于降低应用的总内存需求；继续使用时可能重新载入。

操作当时可用内存从约 2648MiB 增至 2946MiB，增加约 298MiB。全部环境验证完成后一次采样约有 3.97GiB 可用，受应用活动和系统缓存变化影响。浏览器、WPS 文档、当前助手和系统安全服务均保留。

## 常用命令

在项目根目录使用 PowerShell。启动 Blender 界面：

```powershell
.\.venv\Scripts\python.exe tools\blender.py
```

运行缓存测试和查询当前人物配置：

```powershell
.\.venv\Scripts\python.exe -m unittest -v
.\.venv\Scripts\python.exe cache_pipeline.py status
```

重新验证 Blender 单帧；下面使用 factory-startup，不改变个人默认设置：

```powershell
.\.venv\Scripts\python.exe tools\blender.py --background --factory-startup --python tools\smoke_blender.py -- --output work\environment-smoke\workbench
.\.venv\Scripts\python.exe tools\blender.py --background --factory-startup --python tools\smoke_blender.py -- --engine BLENDER_EEVEE_NEXT --output work\environment-smoke\eevee
```

查看已有测试视频的缓存，或启动默认播放器；这是测试图案与提示音，不是人物：

```powershell
.\.venv\Scripts\python.exe cache_pipeline.py status --config work\environment-smoke\config.json
.\.venv\Scripts\python.exe cache_pipeline.py play --config work\environment-smoke\config.json
```

此环境尚未接入人物资产或外部 API。接下来按 DEVELOPMENT.md 步骤 3 建立简化头部场景，再实现自动生成器。

## 下载视频缓存验证

使用下载目录中的 `video_文明重启：荒野榨取花椒籽油和芝麻..._0.mp4` 完成真实视频缓存测试。原文件约 539.5MiB、31 分 9.85 秒，1920×1080、29.97fps、H.264，带 44.1kHz AAC 双声道音频。保留原始内容，不重新编码。

测试使用独立配置 `work/real-video-validation/config.json`，未改动 prototype.json。该配置中的 fps=30 表示整数名义值，精确源帧率另记为 2997/100，不会据此改变导入视频。

验证记录在 `work/real-video-validation/result.json`：导入约 0.934 秒，第二次 prepare 约 0.82 秒（含缓存校验，不是播放器首帧时间）；修改表情配置后未命中，恢复后重新命中。第二次 prepare 即使提供不存在的生成器命令文件仍然成功，证明命中后跳过生成器。源文件导入前后哈希一致。

FFmpeg 对完整 31 分钟视频的画面和音频解码检查已通过，退出码为 0，错误日志为空。解码结果记录在同目录的 decode-result.txt 和 decode-errors.log。

Python 网络 socket 被禁止时，缓存播放路径解析仍成功。系统网络保持连接；这不等于 Windows 媒体播放器的整机断网验收。已调用默认播放器打开缓存，并检测到媒体播放器窗口，声音和观看体验仍需人工确认。

重新播放本次缓存：

```powershell
.\.venv\Scripts\python.exe cache_pipeline.py play --config work\real-video-validation\config.json
```

## 第三步简化人物验证

已用 `tools/create_head_scene.py` 生成无外部资产依赖的测试头部与半身：31 个对象、10868 个网格顶点、简单材质、静态头发、固定镜头、EEVEE 16 采样。该模型是流程测试人偶，不是写实成品。眼部用简化缩放表示眨眼，尚无真实眼睑绑定和语音嘴型。

结果位于 `work/head-scene-v1/`：still/preview.png 为静帧；animation/head-v1.blend 为可编辑场景；animation/head-v1.mp4 为 5 秒无音轨样片；scene-report.json、validation.json、video-probe.json 和 render.log 保存渲染与检查结果。

- 720p 静帧通过，并修正初始镜头裁切问题；已检查睁眼、闭眼和反向转头画面。
- 实际渲染 120 帧，24fps、1280×720，首次动画生成约 126.946 秒。该耗时不等于视频播放帧率。
- 重新加载保存的 .blend，验证头部 ±7° 转动、两次眨眼、呼吸、首尾姿态与测试帧中的头部镜头范围。
- 关闭头发后生成 30 对象 / 10148 顶点版本，确认头发网格可移除；未对该版本另做完整动画渲染。
- MP4 帧数为 120、时长 5 秒，完整解码通过；已导入独立缓存，二次 prepare 命中并跳过生成，默认播放器已启动。

角色控制协议：Z 向上、人物正面为 -Y，单位为米；BodyControl 控制整体位移，HeadControl 控制头部旋转，EyeAperture_-1 / EyeAperture_1 控制简化眼部开合。此阶段使用变换控制器，没有生产级骨架或表情 Shape Key 系统。

重新打开场景或播放缓存：

```powershell
.\.venv\Scripts\python.exe tools\blender.py work\head-scene-v1\animation\head-v1.blend
.\.venv\Scripts\python.exe cache_pipeline.py play --config work\head-scene-v1\animation\cache-config.json
```

## 第四步自动离线生成验证

已接入 renderer.py、render_settings.py、renderer-command.json 与 configs/head-draft.json。首次 prepare 自动完成配置快照、Blender 渲染、FFmpeg 编码、视频流与完整解码检查、缓存发布；再次 prepare 跳过生成器。

实测结果：

- 720p / 24fps / 72 帧（3 秒）/ 静态头发：Blender 阶段约 78.222 秒，编码约 0.553 秒，解码约 0.081 秒。
- 同配置第二次 prepare 约 0.207 秒，即使命令文件不存在仍命中，且没有新增渲染任务。
- 360p / 24fps / 24 帧 / 无头发 / 半秒预录测试音：生成、音频补静音、AAC 音轨检查及完整解码通过；Blender 阶段约 11.189 秒。该音频不是 TTS，也不驱动嘴型。
- 过长音频在 Blender 启动前拒绝，未产生可命中缓存；强制重建进程失败后原有缓存仍通过完整性检查。
- 同一路径的音频内容变化使旧缓存失效，恢复内容后重新命中。代码变化使缓存失效由自动测试覆盖。
- 12 项自动测试通过，覆盖缓存、错误设置、帧数 / 帧率 / 分辨率、音轨缺失 / 过短、旧配置快照和 Windows 换行一致性。

本次端到端记录在 work/offline-validation/result.json。逐任务的配置、.blend、PNG、MP4、渲染日志与报告保留在 work/render-jobs。该目录没有自动容量清理或并发控制。

一条命令生成，再次执行即复用缓存；播放使用同一配置：

```powershell
.\.venv\Scripts\python.exe cache_pipeline.py prepare --config configs\head-draft.json --command-file renderer-command.json
.\.venv\Scripts\python.exe cache_pipeline.py play --config configs\head-draft.json
```

支持修改分辨率、fps、samples、头发开关和动画帧数，未知设置会报错。默认人物配置 prototype.json 和历史导入缓存继续保留。下一步为嘴型控制，再接外部 TTS 与面驱。

## 第五步模拟 TTS 嘴型验证

已自动创建 REST、MBP、A、E、I、O、U、FV 状态，并以 Shape Key 驱动嘴唇、口部和简化下颌。没有 TTS 时间轴时保持闭嘴。人物仍为技术测试人偶，FV 不含真实唇齿接触，尚无舌头或完整口腔。

用系统已有 Microsoft Huihui 中文语音为“爸、妈，啊、诶、衣、哦、乌、飞。”生成测试音频，再按音节拼接模拟 TTS 事件，不调用外部 API。音频 3.628 秒，12 个口型事件、9 段停顿；模拟事件不属于真实强制对齐结果。

验证结果：

- 18 项自动测试通过，覆盖非法 / 重叠时间戳、权重越界、平滑过渡、静音与结束闭嘴、音频哈希 / 时长不一致、改事件时间轴导致缓存失效。
- 重新加载实际 Blender 工程，检查八种状态的几何宽度、开口、权重与 9 段停顿，末帧闭嘴。
- 模拟事件中点到最近 24fps 帧的最大量化偏差为 20.612ms；这不是实测语音音素误差。
- 960×540、24fps、90 帧、3.75 秒，H.264 + AAC，视频与音轨检查及完整解码通过；最终 Blender 阶段约 37.317 秒。
- 所有预设停顿音频采样为零，所有测试音节有有效音频；最终二次 prepare 约 0.154 秒，未创建新渲染任务。已启动缓存播放，语音听感与主观自然度仍需人工评价。

输入、音频、事件、截图与报告位于 work/mock-tts；逐任务场景与视频保留在 work/render-jobs。关键控制器为 MouthLips / MouthInterior 的 Shape Key 与 Head 的 JawOpen，时间基准 t=(frame-1)/fps。

```powershell
.\.venv\Scripts\python.exe tools\mock_tts.py
.\.venv\Scripts\python.exe cache_pipeline.py prepare --config work\mock-tts\render-config.json --command-file renderer-command.json
.\.venv\Scripts\python.exe cache_pipeline.py play --config work\mock-tts\render-config.json
```

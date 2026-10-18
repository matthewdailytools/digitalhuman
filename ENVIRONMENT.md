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

# digitalhuman

初级目标：可设置简化程度，提前生成并缓存，第二次直接播放缓存，模拟实时数字人的观看效果。

环境搭建、各部位验证与后续集成步骤见 [分步开发计划](DEVELOPMENT.md)。

本机已完成的环境安装、验证结果和启动命令见 [本机环境](ENVIRONMENT.md)。

## 简化人物场景

`tools/create_head_scene.py` 用 Blender 自带几何建立测试头部与半身，包含静态网格头发、简化眼部开合、轻微转头和呼吸。资产由脚本生成，无外部贴图或模型依赖。它是流程测试人物，尚非真人级角色；眼部开合采用几何缩放，嘴部保持闭合，尚未实现真实眼睑或语音口型。

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

本仓库已实现 Python 标准库缓存管线和 Blender 离线生成器，支持完整渲染、编码、帧数 / 格式 / 音轨检查、解码后发布缓存。尚未接入 Unreal 或外部 AI API。运行时播放预渲染视频，不在本机实时渲染人物；当前人物没有语音口型。

## 一条命令自动生成

```powershell
.\.venv\Scripts\python.exe cache_pipeline.py prepare --config configs\head-draft.json --command-file renderer-command.json
.\.venv\Scripts\python.exe cache_pipeline.py play --config configs\head-draft.json
```

第一次读取配置快照并调用 Blender → PNG 序列 → H.264 视频 → ffprobe 检查 → 完整解码 → 缓存。第二次同样的 prepare 输出 CACHE HIT，不启动 Blender。工作文件、可编辑场景和日志保留在 work/render-jobs 的独立任务目录。

实际可设置的参数：quality.width / height（偶数）、fps、samples、hair（none / static），performance.frames。初级生成器只支持 draft / simple / bust、固定半身镜头及中性眨眼动作；不支持的选项报错。profiles preview / final、任意人物、表情和 TTS 尚未实现。

预录音频可选：在 performance 增加 audio_file（项目相对路径或绝对路径）。程序记录音频内容哈希，检查时长不超过 frames/fps，较短音频补静音；它只测试音视频合成，不会驱动嘴型。text 必须为空，防止输入台词却生成无声闭嘴视频。

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

## 接下来需要接入

1. 外部 ASR / 对话 / TTS 与面驱适配器，记录模型和声音版本。
2. Unreal 高质量离线后端及更多角色、表情与材质选项。
3. 待机、倾听、回答片段播放器及过渡、取消机制。
4. 中文口型同步及实际画质验收；现有编码与解码检查继续保留。

## 验证

```powershell
python -m unittest -v
```

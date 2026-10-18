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

该缓存配置是本次验证的本地输出；重新运行场景脚本后，需要依据新生成参数和生成器版本重新建立配置并导入。自动生成器与缓存的一步集成属于下一阶段。

## 当前实现边界

本仓库已实现 Python 标准库缓存管线；尚未接入 Blender / Unreal 渲染器或外部 AI API，也没有预置人物视频。运行时播放已渲染的完整视频，不在本机实时渲染人物。必须提供实际视频或外部生成命令后才能看到效果。自动测试只验证缓存行为，不代表完成画质或视频解码验收。

## 配置

编辑 `prototype.json`：角色版本、场景、镜头、质量、台词、声音版本、表情、动作及生成器版本全部参与缓存键计算。任何字段变化都会使旧缓存失效。

建议三档：draft 使用 720p / 24fps、简单皮肤、静态发片、半身；preview 可提高贴图与表情质量；final 用远程 GPU 输出高质量结果。配置参数是传给未来生成器的契约，缓存程序本身不改变模型或视频画质。先把 draft 的生成器跑通，再增加其他档位。

角色、贴图、动作或外部模型发生变化时必须更新对应 revision；使用同一路径替换素材而不更新版本可能误命中。不要把 API 密钥写入配置、命令文件或缓存；由生成器从环境变量读取。

## 第一次：离线生成或导入

最简单的接入方式：从 Blender / Unreal / 外部服务得到包含同步声音的 MP4，然后导入：

```powershell
python cache_pipeline.py import --video "D:\renders\first-human.mp4"
python cache_pipeline.py status
```

也可使用外部生成器。创建一个 JSON 数组格式的命令文件，例如 `renderer-command.json`（下面的 renderer.py 是待实现的适配器，不是仓库已有文件）：

```json
["python", "renderer.py", "--config", "{config}", "--output", "{output}"]
```

```powershell
python cache_pipeline.py prepare --command-file renderer-command.json
```

生成器读取配置快照，调用外部 AI / 离线渲染并等待完成，最后在指定 output 路径写入含同步音频的 MP4。失败不发布新缓存。命中缓存时跳过生成器；显式加 `--force` 才替换，旧版本保留为 `.previous-*`。

首次渲染可以很慢；本机如果连场景都无法加载，仍需使用远端机器。离线不等于没有显存和内存门槛。

## 第二次：模拟实时观看

```powershell
python cache_pipeline.py play
```

缓存完整性校验通过后，Windows 默认视频播放器按视频原有时间轴播放。程序明确输出“缓存回放”；播放路径不调用 API，缺失或损坏时明确报错，不暗中生成。可用 `--dry-run` 仅检查路径。

目前是单片段回放，不支持实时转头、修改台词、无缝拼接或语义级打断。固定镜头下可验证外观、嘴型、表情和毛发的呈现；不能用回放速度推断真实 AI 响应延迟。动态回答必须先生成新视频再缓存。

## 接下来需要接入

1. 外部 ASR / 对话 / TTS 与面驱适配器，记录模型和声音版本。
2. Blender 或 Unreal 的离线生成器，真实执行配置中的简化选项。
3. 待机、倾听、回答片段播放器及过渡、取消机制。
4. 视频格式、时长、音轨、口型同步及实际画质验收。

## 验证

```powershell
python -m unittest -v
```

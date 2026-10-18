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

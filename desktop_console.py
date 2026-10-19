"""Native Windows/Tk test console. Preview uses an owned native FFplay window."""
import base64
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import queue
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox

from cache_pipeline import cache_key
from desktop_controller import Jobs, presets, selection, cache_status, WORK, PROJECT
from render_settings import tool_paths
from playback import ResponseGate
from quality_profiles import PROFILES
from behavior import EXPRESSIONS, MOTIONS, GAZES
from micro_control import manual_plan, describe
from credential_store import ApiCredentials, CredentialError
from realtime_preview import RealtimePreview,CHANNELS


class Player:
    def __init__(self):
        self.process = None

    def play(self, media, loop=False):
        self.stop()
        executable = Path(tool_paths()["ffmpeg"]).with_name("ffplay.exe")
        if not executable.is_file():
            raise ValueError("FFplay 未找到")
        command = [str(executable), "-hide_banner", "-loglevel", "error", "-window_title", "数字人原生预览",
                   "-autoexit", "-x", "960", "-y", "540"]
        if loop:
            command += ["-loop", "0"]
        command.append(str(media))
        WORK.mkdir(parents=True, exist_ok=True)
        with (WORK / "player.log").open("w", encoding="utf-8") as log:
            self.process = subprocess.Popen(command, stdout=log, stderr=log,
                                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        self.process = None


def preview_png(media):
    command = [tool_paths()["ffmpeg"], "-v", "error", "-i", str(media), "-frames:v", "1", "-vf",
               "scale=680:200:force_original_aspect_ratio=decrease,pad=680:200:(ow-iw)/2:(oh-ih)/2:color=0x18201e",
               "-f", "image2pipe", "-vcodec", "png", "pipe:1"]
    return subprocess.run(command, capture_output=True, check=True, timeout=30,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout


class Console:
    def __init__(self, root):
        self.root = root
        self.jobs, self.player = Jobs(), Player()
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.results = queue.Queue()
        self.request_id = 0
        self.summary = None
        self.last_job = None
        self.gate = ResponseGate()
        self.reel_token = None
        self.reel_media = None
        self.context = []
        self.waiting_player = False
        self.busy = False
        self.suppress = False
        self.image = None
        self.live=RealtimePreview();self.live_pending=None
        root.title("数字人测试控制台")
        root.geometry(f"{min(1180, root.winfo_screenwidth()-60)}x{min(820, root.winfo_screenheight()-80)}")
        root.minsize(1020, 660)
        root.configure(bg="#f2f4f1")
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background="#f2f4f1")
        style.configure("TLabel", background="#f2f4f1", foreground="#24352d", font=("Microsoft YaHei UI", 10))
        style.configure("TButton", font=("Microsoft YaHei UI", 10), padding=(10, 5))
        style.configure("Primary.TButton", background="#17694f", foreground="white")
        style.map("Primary.TButton", background=[("active", "#125740"), ("disabled", "#a5b9af")])
        style.configure("TCombobox", padding=5)
        style.configure("Horizontal.TProgressbar", background="#17694f", troughcolor="#dfe7df")
        page = ttk.Frame(root, padding=16)
        page.pack(fill="both", expand=True)
        ttk.Label(page, text="DIGITAL HUMAN LAB / DESKTOP", font=("Segoe UI", 9)).pack(anchor="w")
        title = ttk.Frame(page)
        title.pack(fill="x", pady=(5, 12))
        ttk.Label(title, text="数字人测试控制台", font=("Microsoft YaHei UI", 18, "bold")).pack(side="left")
        ttk.Label(title, text="桌面版 · DeepSeek 对话 · 本地测试语音").pack(side="right")
        main = ttk.Frame(page)
        main.pack(fill="both", expand=True)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)
        tabs = ttk.Notebook(main, width=280)
        tabs.grid(row=0, column=0, sticky="nsw", padx=(0, 18))
        left = ttk.Frame(tabs, padding=8)
        advanced = ttk.Frame(tabs, padding=8)
        ai = ttk.Frame(tabs, padding=8)
        micro = ttk.Frame(tabs, padding=8)
        tabs.add(left, text="渲染")
        tabs.add(advanced, text="表情 / 动作")
        tabs.add(micro, text="五项控制")
        tabs.add(ai, text="AI / 验收")
        realtime=ttk.Frame(tabs,padding=8);tabs.add(realtime,text='实时')
        self.realtime_tab=realtime
        self.tabs, self.micro_tab = tabs, micro
        right = ttk.Frame(main)
        right.grid(row=0, column=1, sticky="nsew")
        self.widgets = []
        self.variables = {name: tk.StringVar(root) for name in ("preset", "resolution", "fps", "samples", "frames", "hair", "camera", "profile", "expression", "motion", "strength", "gaze", "enter", "leave")}
        self.values = {}

        def field(label, key, values=None, parent=None, width=29):
            parent = parent or left
            ttk.Label(parent, text=label).pack(anchor="w", pady=(6, 3))
            if values:
                widget = ttk.Combobox(parent, textvariable=self.variables[key], values=values, state="readonly", width=width)
                self.values[key] = values
            else:
                widget = ttk.Spinbox(parent, from_=2, to=1800, textvariable=self.variables[key], width=width)
            widget.pack(fill="x")
            self.widgets.append((widget, "readonly" if values else "normal"))
            return widget

        self.preset_widget = field("测试场景", "preset", ["模拟中文 TTS / 嘴型", "半身 / 待机动画"])
        self.text_label = ttk.Label(left, text="", wraplength=260, foreground="#52705f")
        self.text_label.pack(anchor="w", pady=10)
        field("分辨率", "resolution", ["640 × 360", "960 × 540", "1280 × 720"])
        for pair in ((('帧率', 'fps', ['24', '30']), ('采样数', 'samples', ['4', '8', '16', '32'])),
                     (('动画帧数', 'frames', None), ('头发', 'hair', ['静态头发', '关闭头发', '简化摆动']))):
            row = ttk.Frame(left)
            row.pack(fill="x")
            for label, key, values in pair:
                cell = ttk.Frame(row)
                cell.pack(side="left", fill="x", expand=True, padx=(0, 4))
                field(label, key, values, cell, 12)
        field("镜头", "camera", ["头部近景", "固定半身"])
        self.duration = ttk.Label(left, text="")
        self.duration.pack(anchor="w", pady=(8, 10))
        self.button(left, "生成 / 复用缓存", lambda: self.start("render"), primary=True)
        self.button(left, "强制重新生成", lambda: self.start("render", True))
        self.button(left, "刷新缓存状态", self.refresh)
        field("质量档位", "profile", ["draft", "preview", "final"], advanced)
        ttk.Label(advanced, text="final 需要远端 GPU，当前不可用", wraplength=255).pack(anchor="w", pady=6)
        field("表情", "expression", list(EXPRESSIONS), advanced)
        field("动作", "motion", list(MOTIONS), advanced)
        field("强度 0—1", "strength", ["0", "0.3", "0.6", "1"], advanced)
        field("眼神", "gaze", list(GAZES), advanced)
        field("进入时间（秒）", "enter", ["0.1", "0.25", "0.5", "1"], advanced)
        field("退出时间（秒）", "leave", ["0.1", "0.25", "0.5", "1"], advanced)
        ttk.Label(ai, text="台词 / 向 DeepSeek 提问", wraplength=250).pack(anchor="w")
        self.prompt = tk.Text(ai, width=27, height=3, font=("Microsoft YaHei UI", 10), wrap="word")
        self.prompt.pack(fill="x", pady=6)
        self.prompt.insert("1.0", "你好，欢迎来到数字人测试。")
        self.provider = tk.StringVar(root, "mock")
        ttk.Combobox(ai, textvariable=self.provider, values=["mock", "deepseek"], state="readonly", width=26).pack(fill="x", pady=4)
        self.model = tk.StringVar(root, os.environ.get("DEEPSEEK_MODEL", "deepseek-flash"))
        ttk.Label(ai, text="DeepSeek 模型（可修改）").pack(anchor="w")
        ttk.Entry(ai, textvariable=self.model).pack(fill="x", pady=4)
        ttk.Label(ai, text="API Key（保存后重启可用）").pack(anchor="w")
        self.secret = tk.StringVar(root)
        entry = ttk.Entry(ai, textvariable=self.secret, show="•")
        entry.pack(fill="x", pady=4)
        self.widgets.append((entry, 'normal'))
        secret_buttons = ttk.Frame(ai)
        secret_buttons.pack(fill='x', pady=3)
        for label, command in (('保存 / 更换', self.set_secret), ('删除密钥', self.delete_secret)):
            button = ttk.Button(secret_buttons, text=label, command=command)
            button.pack(side='left', fill='x', expand=True, padx=(0, 3))
            self.widgets.append((button, 'normal'))
        self.credentials = ApiCredentials()
        self.secret_status = tk.StringVar(root)
        try:
            self.credentials.load()
            self.secret_status.set(self.credentials.status)
        except CredentialError as error:
            self.secret_status.set(str(error))
        ttk.Label(ai, textvariable=self.secret_status, wraplength=255).pack(anchor='w', pady=3)
        self.button(ai, "准备台词（本地测试语音）", lambda: self.prepare_text(False))
        self.button(ai, "对话 → 准备回复语音", lambda: self.prepare_text(True))
        self.button(ai, "对话 → 生成并播放", lambda: self.prepare_text(True, True))
        ttk.Button(ai, text="清空会话上下文", command=lambda: self.context.clear()).pack(fill='x', pady=3)
        ttk.Label(ai, text="mock 为固定模拟回复；语音为系统 SAPI，嘴型按音量近似，非音素对齐。ASR 尚未接入。", wraplength=255).pack(anchor="w", pady=6)
        ttk.Label(micro, text='五项独立控制 · 无对白缓存视频', wraplength=255).pack(anchor='w')
        self.micro_character=tk.StringVar(root,'写实扫描头部' if (PROJECT/'work/realistic-head/latest.json').is_file() else '技术人偶')
        entry=ttk.Combobox(micro,textvariable=self.micro_character,values=['写实扫描头部','技术人偶'],state='readonly')
        entry.pack(fill='x',pady=3);self.widgets.append((entry,'readonly'))
        self.micro_vars = {name: tk.StringVar(root, '0') for name in ('eye_close','smile','mouth_open','nod')}
        grid = ttk.Frame(micro)
        grid.pack(fill='x', pady=5)
        for i, (name, label) in enumerate((('eye_close','闭眼'),('smile','微笑'),('mouth_open','张嘴'),('nod','点头'))):
            cell = ttk.Frame(grid)
            cell.grid(row=i//2, column=i%2, sticky='ew', padx=(0,8), pady=3)
            grid.columnconfigure(i%2, weight=1)
            ttk.Label(cell, text=label+' 0—1').pack(anchor='w')
            entry = ttk.Spinbox(cell, from_=0, to=1, increment=0.1, textvariable=self.micro_vars[name], width=10)
            entry.pack(fill='x')
            self.widgets.append((entry,'normal'))
        self.micro_gaze = tk.StringVar(root,'看镜头')
        self.gaze_values = {'看镜头':[0,0],'画面左':[-1,0],'画面右':[1,0],'向上':[0,1],'向下':[0,-1]}
        ttk.Label(micro, text='注视方向').pack(anchor='w')
        entry = ttk.Combobox(micro, textvariable=self.micro_gaze, values=list(self.gaze_values), state='readonly')
        entry.pack(fill='x', pady=3)
        self.widgets.append((entry,'readonly'))
        self.micro_duration = tk.StringVar(root,'3')
        row = ttk.Frame(micro)
        row.pack(fill='x', pady=3)
        ttk.Label(row,text='手动时长（1—15秒）').pack(side='left')
        entry = ttk.Spinbox(row, from_=1, to=15, increment=0.5, textvariable=self.micro_duration, width=6)
        entry.pack(side='right')
        self.widgets.append((entry,'normal'))
        row=ttk.Frame(micro);row.pack(fill='x')
        self.button(row, '手动生成', lambda:self.prepare_micro(False), primary=True).pack_configure(side='left',expand=True)
        self.button(row, '微笑样板', self.prepare_smile_sample).pack_configure(side='left',expand=True)
        ttk.Separator(micro).pack(fill='x',pady=4)
        ttk.Label(micro,text='AI动作指令（时长写在指令中）').pack(anchor='w')
        self.motion_prompt = tk.Text(micro,width=27,height=3,font=('Microsoft YaHei UI',10),wrap='word')
        self.motion_prompt.pack(fill='x',pady=4)
        self.motion_prompt.insert('1.0','用5秒依次闭眼、看向画面左、微笑、张嘴，最后轻轻点头。')
        self.widgets.append((self.motion_prompt,'normal'))
        entry=ttk.Combobox(micro,textvariable=self.provider,values=['mock','deepseek'],state='readonly')
        entry.pack(fill='x',pady=3)
        self.widgets.append((entry,'readonly'))
        ttk.Label(micro,text='AI模型与密钥在“AI / 验收”。\n写实头发选静态或关闭。\nmock为固定演示。',wraplength=255).pack(anchor='w',pady=3)
        self.button(micro,'AI 指令 → 生成并播放',lambda:self.prepare_micro(True),primary=True)
        ttk.Label(realtime,text='扫描脸实时预览 · 独立 Blender 窗口',wraplength=255).pack(anchor='w')
        self.live_values={name:tk.DoubleVar(root,0) for name in CHANNELS}
        self.live_labels={}
        labels=dict(eye_close='闭眼',smile='微笑',mouth_open='张嘴',nod='点头姿态',gaze_x='注视左右',gaze_y='注视上下')
        for name in ('smile','mouth_open','eye_close','gaze_x','gaze_y','nod'):
            row=ttk.Frame(realtime);row.pack(fill='x',pady=2)
            ttk.Label(row,text=labels[name]).pack(side='left')
            value=tk.StringVar(root,'0.00');self.live_labels[name]=value
            ttk.Label(row,textvariable=value).pack(side='right')
            ttk.Scale(realtime,from_=-1 if name.startswith('gaze') else 0,to=1,
                      variable=self.live_values[name],command=self.live_changed).pack(fill='x')
        self.live_mode=tk.StringVar(root,'快速实体')
        entry=ttk.Combobox(realtime,textvariable=self.live_mode,values=['快速实体','实时材质'],state='readonly')
        entry.pack(fill='x',pady=5);entry.bind('<<ComboboxSelected>>',self.live_changed)
        self.live_hair=tk.BooleanVar(root,False)
        ttk.Checkbutton(realtime,text='显示短发（增加图形负载）',variable=self.live_hair,command=self.live_changed).pack(anchor='w')
        row=ttk.Frame(realtime);row.pack(fill='x',pady=5)
        ttk.Button(row,text='打开实时窗口',command=self.live_start).pack(side='left',expand=True,fill='x')
        ttk.Button(row,text='关闭',command=self.live.stop).pack(side='left')
        row=ttk.Frame(realtime);row.pack(fill='x')
        ttk.Button(row,text='微笑演示',command=lambda:self.live_send(sample=True)).pack(side='left',expand=True,fill='x')
        ttk.Button(row,text='恢复中性',command=self.live_reset).pack(side='left',expand=True,fill='x')
        self.live_status=tk.StringVar(root,'打开窗口后拖动滑块；不生成视频。')
        ttk.Label(realtime,textvariable=self.live_status,wraplength=255).pack(anchor='w',pady=5)
        ttk.Label(realtime,text='快速实体用于动作检查；实时材质为简化 EEVEE 预览，画质与离线成片不同。',wraplength=255).pack(anchor='w')
        tools = ttk.Frame(right)
        tools.pack(fill="x", pady=(0, 8))
        self.badge = ttk.Label(tools, text="检查缓存…", font=("Microsoft YaHei UI", 11, "bold"))
        self.badge.pack(side="left")
        ttk.Button(tools, text='缓存管理', command=self.cache_manage).pack(side='right', padx=(6,0))
        for label, kind in (("步骤验收", "acceptance"), ("自动测试", "tests"), ("模拟 TTS", "mock-tts")):
            button = ttk.Button(tools, text=label, command=lambda task=kind: self.start(task))
            button.pack(side="right", padx=(6, 0))
            self.widgets.append((button, "normal"))
        preview_box = tk.Frame(right, width=680, height=200, bg="#18201e")
        preview_box.pack(fill="x")
        preview_box.pack_propagate(False)
        self.preview = tk.Label(preview_box, text="生成后显示缓存预览", bg="#18201e", fg="#c5d3ca",
                                font=("Microsoft YaHei UI", 13))
        self.preview.pack(fill="both", expand=True)
        controls = ttk.Frame(right)
        controls.pack(fill="x", pady=12)
        self.play_button = ttk.Button(controls, text="播放缓存", command=self.play, style="Primary.TButton")
        self.play_button.pack(side="left")
        ttk.Button(controls, text="停止播放", command=self.stop).pack(side="left", padx=8)
        self.loop = tk.BooleanVar(root, True)
        ttk.Checkbutton(controls, text="循环播放", variable=self.loop).pack(side="left")
        state_controls = ttk.Frame(right)
        state_controls.pack(fill="x", pady=(0, 5))
        reel_button=ttk.Button(state_controls, text="生成四状态演示", command=lambda: self.start('reel'))
        reel_button.pack(side='left', padx=(0,8))
        self.widgets.append((reel_button,'normal'))
        ttk.Button(state_controls, text="播放上次状态演示", command=self.play_reel).pack(side='left')
        ttk.Label(right, text="原生窗口播放；空格暂停。停止阻止旧结果抢播，后台生成可继续缓存。", foreground="#68796f").pack(anchor="w")
        self.status = tk.StringVar(root, "准备就绪")
        ttk.Label(right, textvariable=self.status, wraplength=650).pack(anchor="w", pady=(14, 6))
        self.progress = ttk.Progressbar(right, maximum=100)
        self.progress.pack(fill="x", pady=(0, 10))
        self.result_tabs = ttk.Notebook(right)
        self.result_tabs.pack(fill='both',expand=True)
        log_page, plan_page = ttk.Frame(self.result_tabs), ttk.Frame(self.result_tabs)
        self.result_tabs.add(log_page,text='任务日志')
        self.result_tabs.add(plan_page,text='五项控制计划')
        self.plan_page = plan_page
        self.plan_view = tk.Text(plan_page,height=8,wrap='word',font=('Consolas',9),bg='#e7ede6',fg='#304938',relief='flat',padx=12,pady=10)
        self.plan_view.pack(fill='both',expand=True)
        self.plan_view.insert('end','生成五项控制后，可查看实际执行的动作时间轴和JSON。')
        self.plan_view.configure(state='disabled')
        self.log = tk.Text(log_page, height=8, wrap="word", font=("Consolas", 9), bg="#e7ede6", fg="#304938", relief="flat", padx=12, pady=10)
        self.log.pack(fill="both", expand=True)
        self.log.insert("end", "等待任务。\n模拟时间戳用于测试，不代表真实中文音素对齐精度。")
        self.log.configure(state="disabled")
        for name, variable in self.variables.items():
            variable.trace_add("write", lambda *args, key=name: self.changed(key))
        self.reload_presets()
        root.after(150, self.poll)
        root.after(200,self.live_poll)
        root.protocol("WM_DELETE_WINDOW", self.close)

    def button(self, parent, text, command, primary=False):
        widget = ttk.Button(parent, text=text, command=command, style="Primary.TButton" if primary else "TButton")
        widget.pack(fill="x", pady=4)
        self.widgets.append((widget, "normal"))
        return widget

    def reload_presets(self):
        self.presets = presets()
        names = [entry["name"] for entry in self.presets]
        self.preset_widget.configure(values=names)
        current = self.variables["preset"].get()
        preferred = '五项控制 / 最近结果' if '五项控制 / 最近结果' in names else ('自定义台词 / AI 回复' if '自定义台词 / AI 回复' in names else names[0])
        self.variables["preset"].set(current if current in names else preferred)

    def changed(self, key):
        if self.suppress:
            return
        if key == "preset":
            preset = next(entry for entry in self.presets if entry["name"] == self.variables["preset"].get())
            config = preset["config"]
            self.suppress = True
            self.variables["resolution"].set(f'{config["quality"]["width"]} × {config["quality"]["height"]}')
            for field in ("fps", "samples"):
                self.variables[field].set(str(config["quality"][field]))
            self.variables["frames"].set(str(config["performance"]["frames"]))
            self.variables["hair"].set({"static":"静态头发", "none":"关闭头发", "sway":"简化摆动"}[config["quality"]["hair"]])
            self.variables["profile"].set(config['quality']['profile'])
            for name, default in (("expression","neutral-with-blink"),("strength",0.6),("gaze","camera"),("enter",0.25),("leave",0.25)):
                self.variables[name].set(str(config['performance'].get(name,default)))
            self.variables['motion'].set(config['performance']['motion_revision'])
            self.variables["camera"].set("头部近景" if config["scene"]["camera"] == "head-closeup" else "固定半身")
            self.text_label.configure(text=config["performance"]["text"] or "无对白 · 眨眼、转头与呼吸")
            self.suppress = False
        if key == 'profile':
            profile = self.variables['profile'].get()
            if profile in PROFILES:
                self.suppress = True
                quality = PROFILES[profile]
                self.variables['resolution'].set(f"{quality['width']} × {quality['height']}")
                for name in ('fps','samples'):
                    self.variables[name].set(str(quality[name]))
                self.variables['hair'].set({'static':'静态头发','sway':'简化摆动'}[quality['hair']])
                self.suppress = False
        self.gate.stop()
        self.player.stop()
        self.summary = None
        self.play_button.configure(state="disabled")
        self.request_id += 1
        request = self.request_id
        self.root.after(350, lambda: self.refresh() if request == self.request_id else None)

    def payload(self):
        variables = {name: variable.get() for name, variable in self.variables.items()}
        width, height = map(int, variables["resolution"].split(" × "))
        preset = next(entry["id"] for entry in self.presets if entry["name"] == variables["preset"])
        return {"preset": preset, "settings": {"width": width, "height": height, "fps": int(variables["fps"]),
                "samples": int(variables["samples"]), "frames": int(variables["frames"]),
                "hair": {"静态头发":"static", "关闭头发":"none", "简化摆动":"sway"}[variables["hair"]],
                "profile": variables['profile'], "expression":variables['expression'], "motion":variables['motion'],
                "strength":float(variables['strength']), "gaze":variables['gaze'],
                "enter":float(variables['enter']), "leave":float(variables['leave']),
                "camera": "head-closeup" if variables["camera"] == "头部近景" else "fixed-half-body"}}

    def refresh(self):
        if self.busy:
            return
        self.request_id += 1
        request_id = self.request_id
        try:
            payload = self.payload()
            self.duration.configure(text=f'{payload["settings"]["frames"]} 帧 / {payload["settings"]["fps"]} fps = {payload["settings"]["frames"]/payload["settings"]["fps"]:.2f} 秒')
        except (ValueError, StopIteration):
            self.status.set("请输入有效的测试参数")
            return
        self.badge.configure(text="检查缓存…")
        def work():
            try:
                summary = cache_status(selection(payload))
                image = preview_png(summary["media_path"]) if summary["hit"] else None
                self.results.put((request_id, summary, image, None))
            except Exception as error:
                self.results.put((request_id, None, None, str(error)))
        self.pool.submit(work)

    def start(self, kind, force=False, request=None):
        if self.busy:
            return
        try:
            config = selection(self.payload()) if kind in ("render", "reel") else None
            self.player.stop()
            self.request_id += 1
            self.reel_token = self.gate.begin()
            self.jobs.start(kind, config, force, request)
            self.set_busy(True)
            if kind == 'answer':
                try:
                    self.play_wait_state('thinking')
                except Exception:
                    self.waiting_player=False
            self.status.set("任务启动中…")
            self.progress["value"] = 0
        except Exception as error:
            self.status.set(str(error))

    def set_busy(self, busy):
        self.busy = busy
        for widget, state in self.widgets:
            widget.configure(state="disabled" if busy else state)
        self.play_button.configure(state="disabled" if busy or not self.summary or not self.summary["hit"] else "normal")

    def poll(self):
        while not self.results.empty():
            request_id, summary, image, error = self.results.get_nowait()
            if request_id != self.request_id or self.busy:
                continue
            if error:
                self.summary = None
                self.badge.configure(text="配置需调整")
                self.status.set(error)
                continue
            self.summary = summary
            if summary.get('micro_control'):
                self.show_plan(summary['micro_control'])
            self.badge.configure(text="缓存已就绪" if summary["hit"] else "当前配置尚未生成")
            self.play_button.configure(state="normal" if summary["hit"] else "disabled")
            if image:
                self.image = tk.PhotoImage(data=base64.b64encode(image))
                self.preview.configure(image=self.image, text="", width=680, height=200)
            else:
                self.image = tk.PhotoImage(width=680, height=200)
                self.image.put("#18201e", to=(0, 0, 680, 200))
                self.preview.configure(image=self.image, text="")
            if not self.player.process or self.player.process.poll() is not None:
                self.status.set("配置命中缓存，可直接播放。" if summary["hit"] else "点击生成，离线制作当前配置的视频。")
        job = self.jobs.snapshot()
        if job and self.busy:
            labels = {"starting": "任务启动中", "blender": "Blender 渲染", "encode": "编码", "decode": "完整解码", "cache-hit": "缓存命中"}
            self.status.set(f'{labels.get(job["stage"], job["kind"])} · {job["elapsed"]:.1f}s · {job["frames_done"]} 帧')
            self.progress["value"] = job["progress"]
            self.log.configure(state="normal")
            self.log.delete("1.0", "end")
            self.log.insert("end", "\n".join(job["logs"]))
            self.log.see("end")
            self.log.configure(state="disabled")
            if job["state"] != "running":
                try:
                    self.set_busy(False)
                    if job["state"] == "failed":
                        if self.waiting_player:
                            self.player.stop()
                            self.waiting_player=False
                        self.status.set("任务失败，查看日志；原有缓存保留。")
                    elif job["kind"] == "mock-tts":
                        self.reload_presets()
                        self.status.set("模拟 TTS 已更新，请生成对应视频。")
                    elif job["kind"] == 'answer':
                        may_play=self.gate.accepts(self.reel_token)
                        if self.waiting_player:
                            self.player.stop()
                            self.waiting_player=False
                        if may_play:
                            self.context=json.loads((Path(job['output_dir'])/'result.json').read_text('utf-8'))['context']
                        self.reload_presets()
                        self.variables['preset'].set('自定义台词 / AI 回复')
                        if may_play:
                            answer=json.loads((Path(job['output_dir'])/'answer.json').read_text('utf-8'))
                            verified=cache_status(answer['config'])
                            if not verified['hit']:
                                raise ValueError('回复缓存丢失或损坏，请重新生成')
                            self.player.play(verified['media_path'],False)
                            self.status.set('speaking：正在播放已生成回复。')
                        else:
                            self.status.set('回复已缓存；已停止的旧任务不会抢播。')
                    elif job["kind"] == "text":
                        self.context=json.loads((Path(job['output_dir'])/'result.json').read_text('utf-8'))['context']
                        self.reload_presets()
                        self.variables['preset'].set('自定义台词 / AI 回复')
                        self.status.set('语音准备完成，请点击生成视频。嘴型为音量近似测试。')
                    elif job['kind'] == 'micro':
                        may_play = self.gate.accepts(self.reel_token)
                        output = Path(job['output_dir'])
                        result = json.loads((output/'result.json').read_text('utf-8'))
                        self.reload_presets()
                        self.variables['preset'].set('五项控制 / 最近结果')
                        self.show_plan(result['plan'])
                        self.result_tabs.select(self.plan_page)
                        if may_play:
                            answer = json.loads((output/'answer.json').read_text('utf-8'))
                            verified = cache_status(answer['config'])
                            if not verified['hit']:
                                raise ValueError('五项控制缓存丢失或损坏')
                            self.player.play(verified['media_path'],False)
                            self.status.set(f"五项控制已播放；来源：{result['source']}；视频缓存命中：{result['video_hit']}")
                        else:
                            self.status.set('五项控制已缓存；停止后的任务不会自动播放。')
                    elif job["kind"] == "reel":
                        result=json.loads((Path(job['output_dir'])/'reel.json').read_text('utf-8'))
                        self.reel_media=result['media_path']
                        self.status.set('状态演示已缓存。点击播放；停止后不会自动抢播。')
                    elif job["kind"] == "acceptance":
                        self.status.set('技术验收通过；主观画质和真实外部语音仍需验收。报告位于 work/acceptance/report.json')
                    elif job["kind"] == "tests":
                        self.status.set("自动测试全部通过。")
                    else:
                        self.refresh()
                except Exception as error:
                    self.status.set('任务已结束，预览处理失败：'+str(error))
        self.root.after(200, self.poll)

    def play(self):
        try:
            if not self.summary or not self.summary["hit"]:
                raise ValueError("当前配置无缓存")
            verified=cache_status(selection(self.payload()))
            if not verified['hit']:
                raise ValueError('缓存丢失或损坏，请重新生成')
            self.summary=verified
            self.player.play(verified["media_path"], self.loop.get())
            self.status.set("正在原生预览窗口播放；空格暂停，停止播放可关闭预览。")
        except Exception as error:
            self.status.set(str(error))

    def stop(self):
        self.gate.stop()
        self.waiting_player=False
        self.player.stop()
        self.status.set("已停止本控制台启动的预览。")

    def set_secret(self):
        if self.busy:
            return
        try:
            self.credentials.save(self.secret.get())
            self.secret.set('')
            self.secret_status.set(self.credentials.status)
            self.status.set('密钥已保存 / 更新，立即生效；重启后自动读取。')
        except CredentialError as error:
            self.status.set(str(error))

    def delete_secret(self):
        if self.busy:
            return
        try:
            self.credentials.delete()
            self.secret.set('')
            self.secret_status.set(self.credentials.status)
            self.status.set('已删除本机保存的密钥，并清除当前会话密钥。')
        except CredentialError as error:
            self.status.set(str(error))

    def show_plan(self, plan):
        self.plan_view.configure(state='normal')
        self.plan_view.delete('1.0','end')
        self.plan_view.insert('end',describe(plan)+'\n\n'+json.dumps(plan,ensure_ascii=False,indent=2))
        self.plan_view.configure(state='disabled')

    def prepare_smile_sample(self):
        if self.busy:return
        try:
            from smile_sample import smile_plan
            settings=self.payload()['settings']
            quality={k:settings[k] for k in ('width','height','fps','samples','hair','camera') if k in settings}
            self.micro_character.set('写实扫描头部')
            self.show_plan(smile_plan())
            self.start('micro',request=dict(mode='smile-sample',character='scanned-head',quality=quality))
        except (ValueError,KeyError) as error:
            self.status.set('微笑样板参数无效：'+str(error))

    def live_start(self):
        if self.busy:
            self.live_status.set('请等待当前离线任务完成后打开实时窗口。');return
        try:
            self.player.stop();self.live.start();self.live_send()
        except Exception as error:self.live_status.set(str(error))

    def live_changed(self,*args):
        for name,value in self.live_values.items():self.live_labels[name].set(f'{value.get():.2f}')
        if self.live_pending:self.root.after_cancel(self.live_pending)
        self.live_pending=self.root.after(40,self.live_send)

    def live_send(self,sample=False):
        if self.live_pending:self.root.after_cancel(self.live_pending)
        self.live_pending=None
        try:
            seq=self.live.publish({k:v.get() for k,v in self.live_values.items()},
                                 mode='eevee' if self.live_mode.get()=='实时材质' else 'solid',
                                 hair=self.live_hair.get(),sample=sample)
            if seq is None:self.live_status.set('请先打开实时窗口。')
        except Exception as error:self.live_status.set(str(error))

    def live_reset(self):
        for value in self.live_values.values():value.set(0)
        self.live_changed()

    def live_poll(self):
        try:
            state=self.live.snapshot();phase=state['phase']
            if phase=='running':
                fps=state.get('viewport_draw_fps',0)
                label='微笑演示中' if state.get('sample_playing') else '实时窗口已连接'
                self.live_status.set(f"{label} · 指令 {state.get('seq',0)}\n最近视口绘制约 {fps:.1f} FPS；滑块连续更新。")
            elif phase=='loading':self.live_status.set('正在加载扫描脸，请稍候…')
            elif phase=='stopping':self.live_status.set('正在关闭实时窗口…')
            elif phase=='failed':self.live_status.set('实时预览失败：'+state['error'][:180])
            elif self.live.session:self.live_status.set('实时窗口已关闭，可重新打开。')
        except Exception as error:self.live_status.set(str(error))
        self.root.after(200,self.live_poll)

    def prepare_micro(self, ai):
        if self.busy:
            return
        try:
            # Quality only: do not inherit the previous preset's audio or performance.
            settings = self.payload()['settings']
            quality = {k:v for k,v in settings.items() if k in ('profile','width','height','fps','samples','hair','camera')}
            request = dict(mode='ai' if ai else 'manual',quality=quality,
                           character='scanned-head' if self.micro_character.get()=='写实扫描头部' else 'procedural-head')
            if ai:
                request.update(instruction=self.motion_prompt.get('1.0','end').strip(),provider=self.provider.get(),model=self.model.get())
            else:
                values = {k:float(v.get()) for k,v in self.micro_vars.items()}
                duration = float(self.micro_duration.get())
                gaze = self.gaze_values[self.micro_gaze.get()]
                plan = manual_plan(values,gaze,duration)
                self.show_plan(plan)
                request.update(controls=values,gaze=gaze,duration=duration)
            self.start('micro',request=request)
        except (ValueError, KeyError) as error:
            self.status.set('五项控制参数无效：'+str(error))

    def prepare_text(self, dialogue, autoplay=False):
        if self.busy:
            return
        request=dict(text=self.prompt.get('1.0','end').strip(), dialogue=dialogue,
                     provider=self.provider.get(), model=self.model.get(), profile=self.variables['profile'].get(),
                     expression=self.variables['expression'].get(), motion=self.variables['motion'].get(), context=self.context[-12:],
                     camera='fixed-half-body' if autoplay else ('head-closeup' if self.variables['camera'].get()=='头部近景' else 'fixed-half-body'))
        self.start('answer' if autoplay else 'text',request=request)

    def play_wait_state(self, state):
        from playback import state_config
        from cache_pipeline import lookup
        media=lookup(PROJECT/'.cache/digitalhuman',state_config(state))
        if media:
            self.player.play(media,True)
            self.waiting_player=True

    def play_reel(self):
        if self.busy:
            self.status.set('请等待当前任务完成；可随时停止已有播放。')
            return
        try:
            result=json.loads((WORK/'reel.json').read_text('utf-8'))
            media=Path(result['media_path'])
            from layer_cache import digest
            manifest=json.loads((media.parent/'layer.json').read_text('utf-8'))
            if digest(media) != manifest['files']['reel.mp4']:
                raise ValueError('状态演示缓存损坏，请重新生成')
            self.gate.begin()
            self.player.play(media,False)
            self.status.set(f"上次缓存状态演示（{manifest['identity']['profile']}）：待机 → 倾听 → 思考 → 讲话；120ms 黑场过渡。")
        except Exception as error:
            self.status.set(str(error))

    def cache_manage(self):
        from cache_admin import inventory, clean_previous
        entries=inventory(PROJECT/'.cache/digitalhuman')
        total=sum(e['bytes'] for e in entries)
        previous=sum(e['bytes'] for e in entries if e['previous'])
        if not previous:
            messagebox.showinfo('视频缓存',f'{len(entries)} 项，共 {total/1024**2:.1f} MiB；没有可清理的旧版本。分层缓存另保存在 .cache/layers。',parent=self.root)
        elif not self.busy and messagebox.askyesno('清理旧版本',f'视频缓存共 {total/1024**2:.1f} MiB。删除被替换的旧版本可释放 {previous/1024**2:.1f} MiB。保留当前缓存，是否清理？',parent=self.root):
            removed=clean_previous(PROJECT/'.cache/digitalhuman')
            self.status.set(f'已清理旧版本 {removed/1024**2:.1f} MiB')

    def close(self):
        if self.busy:
            messagebox.showinfo("任务运行中", "请等待当前任务完成后关闭控制台。", parent=self.root)
            return
        self.player.stop()
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.live.stop()
        self.root.destroy()


if __name__ == "__main__":
    import argparse
    parser=argparse.ArgumentParser(description='数字人桌面控制台')
    parser.add_argument('--realtime',action='store_true',help='打开实时页并加载 Blender 预览')
    args=parser.parse_args()
    root = tk.Tk()
    console=Console(root)
    if args.realtime:
        console.tabs.select(console.realtime_tab)
        root.after(250,console.live_start)
    root.mainloop()

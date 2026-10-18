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
               "scale=680:280:force_original_aspect_ratio=decrease,pad=680:280:(ow-iw)/2:(oh-ih)/2:color=0x18201e",
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
        self.busy = False
        self.suppress = False
        self.image = None
        root.title("数字人测试控制台")
        root.geometry(f"{min(1180, root.winfo_screenwidth()-60)}x{min(820, root.winfo_screenheight()-100)}")
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
        ttk.Label(title, text="原生桌面 · 无网页服务 · 外部 API 未连接").pack(side="right")
        main = ttk.Frame(page)
        main.pack(fill="both", expand=True)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)
        left = ttk.Frame(main, padding=(0, 0, 22, 0))
        left.grid(row=0, column=0, sticky="nsw")
        right = ttk.Frame(main)
        right.grid(row=0, column=1, sticky="nsew")
        self.widgets = []
        self.variables = {name: tk.StringVar(root) for name in ("preset", "resolution", "fps", "samples", "frames", "hair", "camera")}
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
                     (('动画帧数', 'frames', None), ('头发', 'hair', ['静态头发', '关闭头发']))):
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
        tools = ttk.Frame(right)
        tools.pack(fill="x", pady=(0, 8))
        self.badge = ttk.Label(tools, text="检查缓存…", font=("Microsoft YaHei UI", 11, "bold"))
        self.badge.pack(side="left")
        for label, kind in (("运行自动测试", "tests"), ("生成模拟 TTS", "mock-tts")):
            button = ttk.Button(tools, text=label, command=lambda task=kind: self.start(task))
            button.pack(side="right", padx=(6, 0))
            self.widgets.append((button, "normal"))
        preview_box = tk.Frame(right, width=680, height=280, bg="#18201e")
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
        ttk.Label(right, text="视频在独立原生窗口播放；空格暂停。停止播放不会取消离线生成。", foreground="#68796f").pack(anchor="w")
        self.status = tk.StringVar(root, "准备就绪")
        ttk.Label(right, textvariable=self.status, wraplength=650).pack(anchor="w", pady=(14, 6))
        self.progress = ttk.Progressbar(right, maximum=100)
        self.progress.pack(fill="x", pady=(0, 10))
        self.log = tk.Text(right, height=8, wrap="word", font=("Consolas", 9), bg="#e7ede6", fg="#304938", relief="flat", padx=12, pady=10)
        self.log.pack(fill="both", expand=True)
        self.log.insert("end", "等待任务。\n模拟时间戳用于测试，不代表真实中文音素对齐精度。")
        self.log.configure(state="disabled")
        for name, variable in self.variables.items():
            variable.trace_add("write", lambda *args, key=name: self.changed(key))
        self.reload_presets()
        root.after(150, self.poll)
        root.protocol("WM_DELETE_WINDOW", self.close)

    def button(self, parent, text, command, primary=False):
        widget = ttk.Button(parent, text=text, command=command, style="Primary.TButton" if primary else "TButton")
        widget.pack(fill="x", pady=4)
        self.widgets.append((widget, "normal"))

    def reload_presets(self):
        self.presets = presets()
        names = [entry["name"] for entry in self.presets]
        self.preset_widget.configure(values=names)
        current = self.variables["preset"].get()
        self.variables["preset"].set(current if current in names else names[0])

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
            self.variables["hair"].set("静态头发" if config["quality"]["hair"] == "static" else "关闭头发")
            self.variables["camera"].set("头部近景" if config["scene"]["camera"] == "head-closeup" else "固定半身")
            self.text_label.configure(text=config["performance"]["text"] or "无对白 · 眨眼、转头与呼吸")
            self.suppress = False
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
                "hair": "static" if variables["hair"] == "静态头发" else "none",
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

    def start(self, kind, force=False):
        try:
            config = selection(self.payload()) if kind == "render" else None
            self.player.stop()
            self.request_id += 1
            self.jobs.start(kind, config, force)
            self.set_busy(True)
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
            self.badge.configure(text="缓存已就绪" if summary["hit"] else "当前配置尚未生成")
            self.play_button.configure(state="normal" if summary["hit"] else "disabled")
            if image:
                self.image = tk.PhotoImage(data=base64.b64encode(image))
                self.preview.configure(image=self.image, text="", width=680, height=280)
            else:
                self.image = tk.PhotoImage(width=680, height=280)
                self.image.put("#18201e", to=(0, 0, 680, 280))
                self.preview.configure(image=self.image, text="")
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
                self.set_busy(False)
                if job["state"] == "failed":
                    self.status.set("任务失败，查看日志；原有缓存保留。")
                elif job["kind"] == "mock-tts":
                    self.reload_presets()
                    self.status.set("模拟 TTS 已更新，请生成对应视频。")
                elif job["kind"] == "tests":
                    self.status.set("自动测试全部通过。")
                else:
                    self.refresh()
        self.root.after(200, self.poll)

    def play(self):
        try:
            if not self.summary or not self.summary["hit"]:
                raise ValueError("当前配置无缓存")
            self.player.play(self.summary["media_path"], self.loop.get())
            self.status.set("正在原生预览窗口播放；空格暂停，停止播放可关闭预览。")
        except Exception as error:
            self.status.set(str(error))

    def stop(self):
        self.player.stop()
        self.status.set("已停止本控制台启动的预览。")

    def close(self):
        if self.busy:
            messagebox.showinfo("任务运行中", "请等待当前任务完成后关闭控制台。", parent=self.root)
            return
        self.player.stop()
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    Console(root)
    root.mainloop()

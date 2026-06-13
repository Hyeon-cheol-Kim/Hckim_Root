"""PC → iPhone USB 파일 전송기 (tkinter GUI)"""

import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

from transfer import (
    ALLOWED_EXTENSIONS,
    TARGET_FOLDER,
    check_device_status,
    transfer_files,
    is_allowed,
)

C_BG      = '#1e1e2e'
C_PANEL   = '#2a2a3e'
C_ACCENT  = '#4fa3e0'
C_GREEN   = '#27ae60'
C_RED     = '#e74c3c'
C_TEXT    = '#ecf0f1'
C_SUBTEXT = '#95a5a6'
C_BTN     = '#34495e'


def _btn(parent, text, cmd, **kw):
    defaults = dict(bg=C_BTN, fg=C_TEXT, relief=tk.FLAT, padx=8, pady=3, cursor='hand2')
    defaults.update(kw)
    return tk.Button(parent, text=text, command=cmd, **defaults)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PC → iPhone 파일 전송기")
        self.geometry("740x560")
        self.resizable(True, True)
        self.configure(bg=C_BG)

        self.selected_files: list[str] = []
        self._transfer_running = False

        self._build_ui()
        self._refresh_device()

    # ── UI 구성 ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_header()
        self._build_device_bar()
        self._build_file_panel()
        self._build_transfer_bar()

    def _build_header(self):
        hdr = tk.Frame(self, bg=C_ACCENT, pady=8)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="📱  PC → iPhone 파일 전송기",
                 font=('Helvetica', 15, 'bold'),
                 fg='white', bg=C_ACCENT).pack()
        ext_str = '  '.join(sorted(ALLOWED_EXTENSIONS))
        tk.Label(hdr, text=f"지원 형식: {ext_str}",
                 font=('Helvetica', 9), fg='#d0e8f8', bg=C_ACCENT).pack()

    def _build_device_bar(self):
        bar = tk.Frame(self, bg=C_PANEL, pady=6)
        bar.pack(fill=tk.X, padx=8, pady=(6, 0))

        tk.Label(bar, text="기기 상태", font=('Helvetica', 10, 'bold'),
                 fg=C_TEXT, bg=C_PANEL, width=8, anchor='w').pack(side=tk.LEFT, padx=(8, 4))

        self._device_dot = tk.Label(bar, text="●", fg='orange', bg=C_PANEL, font=('Helvetica', 14))
        self._device_dot.pack(side=tk.LEFT, padx=(0, 4))

        self._device_var = tk.StringVar(value="확인 중...")
        tk.Label(bar, textvariable=self._device_var,
                 fg=C_TEXT, bg=C_PANEL, font=('Helvetica', 10)).pack(side=tk.LEFT)

        _btn(bar, "새로고침", self._refresh_device).pack(side=tk.RIGHT, padx=8)

        # iTunes 없는 경우 안내 버튼
        _btn(bar, "iTunes 없이 설치하는 방법", self._show_driver_help,
             bg='#2c4a2c', fg='#7ecf7e').pack(side=tk.RIGHT, padx=4)

    def _build_file_panel(self):
        outer = tk.LabelFrame(self, text=" 전송 파일 목록 ",
                              bg=C_BG, fg=C_SUBTEXT,
                              font=('Helvetica', 10))
        outer.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        btn_row = tk.Frame(outer, bg=C_BG)
        btn_row.pack(fill=tk.X, pady=(4, 2))
        _btn(btn_row, "+ 파일 추가",   self._add_files).pack(side=tk.LEFT, padx=3)
        _btn(btn_row, "− 선택 제거",   self._remove_selected).pack(side=tk.LEFT, padx=3)
        _btn(btn_row, "✕ 전체 초기화", self._clear_files).pack(side=tk.LEFT, padx=3)

        list_frame = tk.Frame(outer, bg=C_BG)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        sb = tk.Scrollbar(list_frame, bg=C_PANEL)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        self._listbox = tk.Listbox(list_frame, yscrollcommand=sb.set,
                                   selectmode=tk.EXTENDED,
                                   bg=C_PANEL, fg=C_TEXT,
                                   selectbackground=C_ACCENT,
                                   selectforeground='white',
                                   borderwidth=0, highlightthickness=0,
                                   font=('Courier', 10))
        self._listbox.pack(fill=tk.BOTH, expand=True)
        sb.config(command=self._listbox.yview)

        self._count_var = tk.StringVar(value="파일 0개 선택됨")
        tk.Label(outer, textvariable=self._count_var,
                 fg=C_SUBTEXT, bg=C_BG, font=('Helvetica', 9)).pack(anchor='e', padx=4)

    def _build_transfer_bar(self):
        bot = tk.Frame(self, bg=C_BG, pady=4)
        bot.pack(fill=tk.X, padx=8, pady=(0, 8))

        tk.Label(bot, text=f"저장 경로: iPhone 내부 저장소 → {TARGET_FOLDER}/",
                 fg=C_SUBTEXT, bg=C_BG, font=('Helvetica', 9)).pack(anchor='w')

        self._progress = ttk.Progressbar(bot, mode='determinate', maximum=100)
        self._progress.pack(fill=tk.X, pady=3)

        self._status_var = tk.StringVar(value="준비")
        tk.Label(bot, textvariable=self._status_var,
                 fg=C_SUBTEXT, bg=C_BG, font=('Helvetica', 9)).pack(anchor='w')

        self._transfer_btn = _btn(bot, "  iPhone으로 전송  ",
                                   self._start_transfer,
                                   bg=C_GREEN, fg='white',
                                   font=('Helvetica', 12, 'bold'), pady=6)
        self._transfer_btn.pack(fill=tk.X, pady=(4, 0))

    # ── 기기 상태 ────────────────────────────────────────────────────────────

    def _refresh_device(self):
        self._device_var.set("확인 중...")
        self._device_dot.config(fg='orange')
        threading.Thread(target=self._check_device_thread, daemon=True).start()

    def _check_device_thread(self):
        ok, msg = check_device_status()
        color = C_GREEN if ok else C_RED
        self.after(0, lambda: self._device_var.set(msg))
        self.after(0, lambda: self._device_dot.config(fg=color))

    def _show_driver_help(self):
        msg = (
            "iTunes 없이 iPhone USB 드라이버 설치 방법\n"
            "─────────────────────────────────────────\n\n"
            "[Windows 10 / 11]\n"
            "  Microsoft Store에서 'Apple Devices' 앱을 검색하여\n"
            "  무료 설치하면 iTunes 없이 드라이버만 설치됩니다.\n\n"
            "[설치 후]\n"
            "  iPhone을 USB로 연결 → '신뢰' 버튼 탭 → 새로고침\n\n"
            "[macOS]\n"
            "  Finder가 자동으로 드라이버 역할을 하므로\n"
            "  별도 설치 불필요합니다.\n\n"
            "[Linux]\n"
            "  sudo apt install libimobiledevice-utils usbmuxd\n"
            "  sudo systemctl start usbmuxd"
        )
        messagebox.showinfo("iTunes 없이 설치하는 방법", msg)

    # ── 파일 조작 ────────────────────────────────────────────────────────────

    def _add_files(self):
        ext_pattern = ' '.join(f'*{e}' for e in sorted(ALLOWED_EXTENSIONS))
        paths = filedialog.askopenfilenames(
            title="전송할 파일 선택",
            filetypes=[
                ("지원 파일", ext_pattern),
                ("텍스트 (.txt)", "*.txt"),
                ("PDF (.pdf)", "*.pdf"),
                ("HTML (.html)", "*.html"),
                ("Python (.py)", "*.py"),
                ("C 소스 (.c)", "*.c"),
                ("C++ 소스 (.cpp)", "*.cpp"),
                ("Java (.java)", "*.java"),
                ("배치 파일 (.bat)", "*.bat"),
                ("쉘 스크립트 (.sh)", "*.sh"),
                ("모든 파일", "*.*"),
            ]
        )
        rejected = []
        for p in paths:
            if p in self.selected_files:
                continue
            if is_allowed(p):
                self.selected_files.append(p)
                self._listbox.insert(tk.END, f"  {Path(p).name}")
            else:
                rejected.append(Path(p).name)

        if rejected:
            messagebox.showwarning(
                "지원하지 않는 형식",
                "다음 파일은 지원되지 않아 제외되었습니다:\n" + '\n'.join(rejected)
            )
        self._update_count()

    def _remove_selected(self):
        for i in reversed(self._listbox.curselection()):
            self._listbox.delete(i)
            self.selected_files.pop(i)
        self._update_count()

    def _clear_files(self):
        self._listbox.delete(0, tk.END)
        self.selected_files.clear()
        self._update_count()

    def _update_count(self):
        self._count_var.set(f"파일 {len(self.selected_files)}개 선택됨")

    # ── 전송 ────────────────────────────────────────────────────────────────

    def _start_transfer(self):
        if self._transfer_running:
            return
        if not self.selected_files:
            messagebox.showwarning("파일 없음", "전송할 파일을 선택해 주세요.")
            return
        self._transfer_running = True
        self._transfer_btn.config(state=tk.DISABLED, bg=C_BTN)
        self._progress['value'] = 0
        threading.Thread(target=self._transfer_thread, daemon=True).start()

    def _transfer_thread(self):
        try:
            def on_status(msg):
                self.after(0, lambda m=msg: self._status_var.set(m))

            def on_progress(cur, tot):
                pct = int(cur / tot * 100) if tot else 0
                self.after(0, lambda p=pct: self._progress.configure(value=p))

            success, failures = transfer_files(
                self.selected_files,
                progress_callback=on_progress,
                status_callback=on_status,
            )

            def _done():
                self._progress['value'] = 100
                if failures:
                    fail_lines = '\n'.join(f"  • {n}: {e}" for n, e in failures)
                    self._status_var.set(f"완료 ({success}개 성공, {len(failures)}개 실패)")
                    messagebox.showwarning(
                        "일부 실패",
                        f"{success}개 성공, {len(failures)}개 실패:\n{fail_lines}"
                    )
                else:
                    self._status_var.set(f"완료! {success}개 파일 전송 성공 ✓")
                    messagebox.showinfo(
                        "전송 완료",
                        f"{success}개 파일이\niPhone → {TARGET_FOLDER}/\n에 저장되었습니다."
                    )

            self.after(0, _done)

        except Exception as exc:
            err = str(exc)
            self.after(0, lambda e=err: self._status_var.set(f"오류: {e}"))
            self.after(0, lambda e=err: messagebox.showerror(
                "전송 오류",
                f"오류가 발생했습니다:\n\n{e}\n\n"
                "확인 사항:\n"
                "  1. iPhone이 USB로 연결되어 있는지\n"
                "  2. iPhone에서 '신뢰' 버튼을 눌렀는지\n"
                "  3. Apple 드라이버가 설치되어 있는지\n"
                "     (iTunes 또는 Microsoft Store의 'Apple Devices' 앱)"
            ))
        finally:
            self.after(0, self._reset_btn)

    def _reset_btn(self):
        self._transfer_running = False
        self._transfer_btn.config(state=tk.NORMAL, bg=C_GREEN)


if __name__ == '__main__':
    app = App()
    app.mainloop()

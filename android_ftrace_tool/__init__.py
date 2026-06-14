"""
android_ftrace_tool
===================
Android 커널 ftrace 로그를 선택/수집/저장하는 도구.

구조(UI 와 로직 분리):
  - core.py : adb/ftrace 제어 순수 로직 (UI 입출력 없음, GUI 재사용 가능)
  - cli.py  : 대화형 콘솔 UI
  - (향후) gui.py : Windows GUI 확장 시 core.py 를 그대로 재사용

실행:
  python -m android_ftrace_tool
"""

from .core import (Adb, Ftrace, CaptureSession, Device, AdbError,
                   STORAGE_EVENT_GROUPS, FLOW_PRESET_ORDER, EVENT_BUNDLES)

__all__ = ["Adb", "Ftrace", "CaptureSession", "Device", "AdbError",
           "STORAGE_EVENT_GROUPS", "FLOW_PRESET_ORDER", "EVENT_BUNDLES"]
__version__ = "0.1.0"

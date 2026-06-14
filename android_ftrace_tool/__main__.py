"""
패키지 실행 진입점.
    python -m android_ftrace_tool
"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())

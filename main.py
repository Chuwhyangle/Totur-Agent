"""阶段 1 的本地环境检查脚本。

这个文件在项目根目录下，主要用途是确认：
1. Python 能正常运行。
2. 当前使用的是哪个 Python 解释器。
3. 虚拟环境是否已经激活。

注意：
这个文件不是 FastAPI 后端入口。
真正的后端应用入口在 app/main.py。
"""

import os
import sys


def main():
    print("Python is working.")
    print("Python version:", sys.version)
    print("Python executable:", sys.executable)
    print("Virtual env:", os.environ.get("VIRTUAL_ENV", "not activated"))

if __name__ == "__main__":
    main()

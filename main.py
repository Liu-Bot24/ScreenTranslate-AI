#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ScreenTranslate-AI 根目录入口点

这是应用程序的主要入口点，负责导入和启动主应用程序。
支持直接运行和模块导入两种方式。
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    # 导入主程序模块
    from src.main import main

    if __name__ == "__main__":
        # 直接运行时启动主程序
        sys.exit(main())

except ImportError as e:
    print(f"导入模块失败: {e}")
    print("请确保所有依赖都已正确安装。")
    print("运行 'pip install -r requirements.txt' 安装依赖。")
    sys.exit(1)

except Exception as e:
    print(f"程序启动失败: {e}")
    sys.exit(1)
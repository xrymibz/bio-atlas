#!/usr/bin/env python3
"""
A股风向标 - 启动入口
"""
import os
import sys

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5001"))
    host = os.getenv("HOST", "0.0.0.0")
    debug = os.getenv("DEBUG", "false").lower() == "true"

    print(f"[启动] A股风向标 API  http://{host}:{port}")
    app.run(host=host, port=port, debug=debug, threaded=True)

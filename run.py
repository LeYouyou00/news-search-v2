"""应用入口"""
import sys
import os

# 切换到项目根目录
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

import uvicorn

if __name__ == '__main__':
    uvicorn.run(
        'app:create_app',
        host='127.0.0.1',
        port=8000,
        reload=True,
        reload_dirs=[os.path.dirname(os.path.abspath(__file__))],
        factory=True,
    )

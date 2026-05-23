#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
mbot 商家智能体 - CLI 入口
"""
import asyncio
import sys
import os

project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'src'))

from mbot import MbotSession, run_health_check_standalone

def main():
    if len(sys.argv) > 1 and sys.argv[1].strip().lower() == "health":
        exit(run_health_check_standalone())
    session = MbotSession()
    asyncio.run(session.run())


if __name__ == "__main__":
    main()

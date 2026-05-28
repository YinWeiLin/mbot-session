#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
mbot 商家智能体 - CLI 交互层
"""
import asyncio
import sys
import os

project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "src"))

from datetime import datetime
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table
from config import LLM_CONFIG, RESILIENCE_CONFIG
from config_agentscope import init_agentscope
from utils.circuit_breaker import CircuitOpenError
from utils.llm_resilience import run_health_check as check_llm_health
from mbot import MbotSession


class CliRunner:
    """CLI 交互层，负责终端 IO，调用 MbotSession 处理业务"""

    def __init__(self):
        self.console = Console()
        self.session: MbotSession = None

    def _print_welcome(self):
        self.console.print("\n[bold cyan]🤖 mbot 商家智能体[/bold cyan]\n", style="bold")

    def _print_help(self):
        table = Table(title="命令列表", show_header=True, header_style="bold magenta")
        table.add_column("命令", style="cyan", width=20)
        table.add_column("说明", style="white")
        table.add_row("help", "显示此帮助信息")
        table.add_row("status", "查看当前状态和记忆")
        table.add_row("health", "检查 LLM 服务是否可用")
        table.add_row("clear", "清空短期记忆（保留长期记忆）")
        table.add_row("preferences", "查看用户偏好")
        table.add_row("exit", "退出程序")
        self.console.print(table)

    def _show_status(self):
        st = self.session.memory_manager.short_term.get_statistics()

        table = Table(title="记忆状态", show_header=True, header_style="bold magenta")
        table.add_column("类型", style="cyan")
        table.add_column("状态", style="white")
        table.add_row("短期记忆", f"{st['total_messages']} 条消息")
        table.add_row("已加载智能体", f"{len(self.session._agent_cache)} 个")
        self.console.print(table)
        self.console.print()

        recent = self.session.memory_manager.short_term.get_recent_context(n_turns=5)
        if recent:
            dtable = Table(title="最近对话 (最多5轮)", show_header=True, header_style="bold cyan")
            dtable.add_column("角色", style="cyan", width=8)
            dtable.add_column("内容", style="white", width=60)
            dtable.add_column("时间", style="dim", width=12)
            for msg in recent:
                role = "👤 用户" if msg["role"] == "user" else "🤖 助手"
                content = msg["content"][:100] + "..." if len(msg["content"]) > 100 else msg["content"]
                ts = ""
                if msg.get("timestamp"):
                    try:
                        ts = datetime.fromisoformat(msg["timestamp"]).strftime("%H:%M:%S")
                    except Exception:
                        pass
                dtable.add_row(role, content, ts)
            self.console.print(dtable)
            self.console.print()

    def _show_preferences(self):
        prefs = self.session.memory_manager.long_term.get_preference()
        table = Table(title="用户偏好", show_header=True, header_style="bold magenta")
        table.add_column("类型", style="cyan")
        table.add_column("值", style="white")
        for key, value in prefs.items():
            if value:
                table.add_row(key, str(value))
        self.console.print(table)

    async def _run_health_check(self):
        if self.session and self.session.circuit_breaker:
            status = self.session.circuit_breaker.get_status()
            self.console.print(f"[bold]熔断器[/bold]: {status['state']}", style="cyan")
        ok, msg = await check_llm_health(
            base_url=LLM_CONFIG["base_url"],
            api_key=LLM_CONFIG["api_key"],
            model_name=LLM_CONFIG["model_name"],
            timeout_sec=RESILIENCE_CONFIG.get("health_check_timeout_sec", 10.0),
        )
        if ok:
            self.console.print("LLM 服务: [green]正常[/green]", style="bold")
        else:
            self.console.print(f"LLM 服务: [red]不可用[/red] - {msg}", style="bold")
        self.console.print()

    async def run(self):
        self._print_welcome()

        user_id = Prompt.ask("用户ID", default="default_user")
        self.session = MbotSession(user_id=user_id)

        with self.console.status("初始化中...", spinner="dots"):
            init_agentscope()
            await self.session.init()

        self.console.print(
            f"✓ 就绪 (用户: {self.session.user_id} / ssid: {self.session.session_id}) — 输入 help 查看帮助\n",
            style="green",
        )

        while True:
            try:
                user_input = Prompt.ask("\n[cyan]>[/cyan]")
                if not user_input.strip():
                    continue

                cmd = user_input.strip().lower()

                if cmd == "exit":
                    self.session.end_session()
                    self.console.print("再见！", style="cyan")
                    break
                elif cmd == "help":
                    self._print_help()
                elif cmd == "status":
                    self._show_status()
                elif cmd == "health":
                    await self._run_health_check()
                elif cmd == "clear":
                    self.session.memory_manager.short_term.clear()
                    self.console.print("✓ 已清空短期记忆", style="green")
                elif cmd == "preferences":
                    self._show_preferences()
                else:
                    with self.console.status("思考中...", spinner="dots"):
                        reply = await self.session.process_query(user_input)
                    self.console.print(f"\n{reply}\n")

            except KeyboardInterrupt:
                self.console.print("\n使用 'exit' 退出", style="dim")
            except CircuitOpenError:
                self.console.print("\n[bold yellow]⚠ 服务暂时不可用，请稍后再试。[/bold yellow]", style="dim")
            except Exception as e:
                self.console.print(f"\n错误: {e}", style="red")


def _health_check_standalone() -> int:
    """独立健康检查，不进入交互式 CLI（供 `python cli.py health` 使用）"""
    init_agentscope()
    ok, msg = asyncio.run(check_llm_health(
        base_url=LLM_CONFIG["base_url"],
        api_key=LLM_CONFIG["api_key"],
        model_name=LLM_CONFIG["model_name"],
        timeout_sec=RESILIENCE_CONFIG.get("health_check_timeout_sec", 10.0),
    ))
    if ok:
        print("健康检查通过 ✅")
        return 0
    print(f"FAIL: {msg}")
    return 1


def main():
    if len(sys.argv) > 1 and sys.argv[1].strip().lower() == "health":
        exit(_health_check_standalone())
    asyncio.run(CliRunner().run())


if __name__ == "__main__":
    main()

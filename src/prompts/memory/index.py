def get_long_term_summary_prompt(history_str: str) -> str:
    return f"""请总结以下历史对话记录中的关键内容，包括：
1. 用户咨询过的课程或产品
2. 用户提及的备考信息（考试类型、阶段、预算等）
3. 用户询问过的重要问题
4. 其他重要的上下文信息

【历史聊天记录】
{history_str}

请用简洁的语言总结（不超过200字）："""

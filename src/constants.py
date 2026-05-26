"""业务常量"""

from enum import IntEnum


# 会话阶段：随便看看 → 认真考虑 → 准备行动（单向递进，不可后退）
class SessionStage(IntEnum):
    LOOKING = 0
    CONSIDERING = 1
    ACTING = 2

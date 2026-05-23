import logging
import os
from datetime import datetime


def setup_logger(session_id: str, project_root: str, user_id: str, model_name: str) -> None:
    log_dir = os.path.join(project_root, "data", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"{session_id}.log")

    # 写入第一行元信息
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(f"# session_id={session_id} user_id={user_id} model={model_name} started_at={datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(log_file, mode="a", encoding="utf-8"),
        ]
    )

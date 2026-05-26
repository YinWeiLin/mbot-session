"""
文档预处理脚本：按语义段落切分，注入父标题，输出到 documents_structured/
运行一次即可，结果存盘，init_knowledge_base.py 读结构化版本。
"""
import re
from pathlib import Path

current_dir = Path(__file__).parent
skill_root = current_dir.parent
input_dir = skill_root / "data" / "documents"
output_dir = skill_root / "data" / "documents_structured"
output_dir.mkdir(parents=True, exist_ok=True)
old_files = list(output_dir.glob("*.txt"))
for f in old_files:
    f.unlink()
if old_files:
    print(f"已清空 {len(old_files)} 个旧文件\n")


def split_by_headings(text: str, doc_title: str) -> list[str]:
    """
    按标题行切分文档，每个 section 注入父标题作为上下文锚点。
    支持三种标题格式：
      - 一、二、三... 中文数字序号
      - 【标题】 方括号
      - **标题** Markdown 加粗
    单个 section 超过 500 字时按空行段落二次切分。
    """
    lines = text.split("\n")
    chunks = []
    current_heading = doc_title
    current_body: list[str] = []
    heading_re = re.compile(
        r"^\s*(?:"
        r"#{1,3}\s+(.+)"                          # # ## ### Markdown 标题
        r"|\*\*(.+?)\*\*"                          # **标题**
        r"|【(.+?)】"                              # 【标题】
        r"|[一二三四五六七八九十百]+[、.．]\s*(.+)" # 一、标题
        r"|\d+[、.．]\s*(.+?)[：:]\s*$"           # 1、姓名：
        r")\s*$"
    )

    def flush(heading: str, body: list[str]):
        content = "\n".join(body).strip()
        if not content:
            return
        full = f"【{heading}】\n{content}"
        if len(full) <= 500:
            chunks.append(full)
            return
        # 超长时按空行段落二次切分
        paragraphs = re.split(r"\n{2,}", content)
        buf = f"【{heading}】\n"
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            if len(buf) + len(para) + 1 <= 500:
                buf += para + "\n"
            else:
                if buf.strip():
                    chunks.append(buf.strip())
                buf = f"【{heading}（续）】\n{para}\n"
        if buf.strip():
            chunks.append(buf.strip())

    for line in lines:
        m = heading_re.match(line)
        if m:
            flush(current_heading, current_body)
            current_heading = (m.group(1) or m.group(2) or m.group(3) or m.group(4) or m.group(5) or line).strip()
            current_body = []
        else:
            current_body.append(line)

    flush(current_heading, current_body)
    return chunks


def process_file(file_path: Path) -> int:
    text = file_path.read_text(encoding="utf-8").strip()
    lines = text.split("\n")
    doc_title = lines[0].strip().lstrip("#").strip() if lines else file_path.stem

    chunks = split_by_headings(text, doc_title)

    out_path = output_dir / file_path.name
    with open(out_path, "w", encoding="utf-8") as f:
        for i, chunk in enumerate(chunks):
            f.write(chunk)
            if i < len(chunks) - 1:
                f.write("\n\n---\n\n")

    return len(chunks)


def main():
    doc_files = sorted(input_dir.glob("*.txt"))
    if not doc_files:
        print(f"❌ 未找到文档：{input_dir}")
        return

    print(f"输出目录：{output_dir}\n")
    total = 0
    for f in doc_files:
        n = process_file(f)
        total += n
        print(f"  ✓ {f.name}  →  {n} chunks")

    print(f"\n合计 {total} 个 chunks，已写入 {output_dir}")


if __name__ == "__main__":
    main()

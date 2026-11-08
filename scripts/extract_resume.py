"""简历文本提取：支持 .txt/.md/.docx/.pdf（PDF 依赖 pypdf/PyPDF2/pdftotext）。

用法：
  python scripts/extract_resume.py --file "C:/path/resume.pdf" --out runs/x/resume-text.json
  python scripts/extract_resume.py --text-file pasted.txt
  python scripts/extract_resume.py --text "……"
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))
import caree_common as c  # noqa: E402

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def read_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    paragraphs = []
    for paragraph in root.iter(f"{W_NS}p"):
        text = "".join(node.text or "" for node in paragraph.iter(f"{W_NS}t")).strip()
        if text:
            paragraphs.append(text)
    return "\n".join(paragraphs)


def read_pdf(path: Path) -> str:
    reader_cls = None
    try:
        from pypdf import PdfReader as reader_cls  # type: ignore
    except Exception:
        try:
            from PyPDF2 import PdfReader as reader_cls  # type: ignore
        except Exception:
            reader_cls = None
    if reader_cls is not None:
        reader = reader_cls(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", str(path), "-"],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except FileNotFoundError:
        pass
    c.die(
        "当前环境无法解析 PDF。两个办法：1) 安装 pypdf（pip install pypdf）或 pdftotext；"
        "2) 让宿主 agent 用其文件读取能力读取 PDF，把文本写入 txt 后使用 --text-file。"
    )


def main():
    ap = argparse.ArgumentParser(description="提取简历文本")
    ap.add_argument("--file", help="简历文件路径（txt/md/docx/pdf）")
    ap.add_argument("--text", help="直接传入简历文本")
    ap.add_argument("--text-file", help="从文本文件读取简历")
    ap.add_argument("--out", required=True, help="输出 JSON 路径")
    args = ap.parse_args()

    source = ""
    if args.text:
        text = args.text
        source = "inline"
    elif args.text_file:
        source = args.text_file
        text = Path(args.text_file).read_text(encoding="utf-8")
    elif args.file:
        path = Path(args.file).resolve()
        if not path.exists():
            c.die(f"文件不存在: {path}")
        source = str(path)
        suffix = path.suffix.lower()
        if suffix in (".txt", ".md", ".markdown"):
            text = path.read_text(encoding="utf-8", errors="ignore")
        elif suffix == ".docx":
            text = read_docx(path)
        elif suffix == ".pdf":
            text = read_pdf(path)
        else:
            c.die(f"不支持的格式: {suffix}；支持 txt/md/docx/pdf")
    else:
        c.die("需要 --file / --text / --text-file 之一")

    text = text.strip()
    if not text:
        c.die("提取到的文本为空")
    out = Path(args.out).resolve()
    c.write_json(out, {
        "source": source,
        "chars": len(text),
        "extracted_at": c.now_iso(),
        "text": text,
    })
    c.emit({"out": str(out), "chars": len(text), "preview": text[:160]})


if __name__ == "__main__":
    main()

"""OpenDataLoader PDF extractor (اختياري) — بديل مرخّص عالي الدقة لتحليل PDF.

التحقق الحي: opendataloader-pdf 2.5.12 = غلاف Python لأداة Java (جرة مضمنة،
تحتاج JVM متاحًا في PATH). الواجهة: ``opendataloader_pdf.run(input_path,
output_folder=..., generate_markdown=..., no_json=...)``.

الترخيص: Apache-2.0 — آمن للدمج (بخلاف pymupdf/AGPL الموجود في
requirements.txt الأساسي؛ هذا الملف اختياري ولا يفرض أي اعتماد جديد
إلا بتنصيب ``opendataloader-pdf`` صراحة).

السياسة: نفس سياسة محركات ocr-core — الفشل يعيد ``{"error": ...}`` ولا يرفع
استثناء أبدًا، بلا أرقام ثقة مختلقة (الثقة تأتي فقط من مخرجات JSON إن وُجدت).
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import time
from pathlib import Path
from typing import Any, Optional


def is_available() -> bool:
    """الحزمة مثبتة + JVM موجود (الجرة تعمل عبر java)."""
    return (
        importlib.util.find_spec("opendataloader_pdf") is not None
        and shutil.which("java") is not None
    )


def extract_pdf(
    pdf_path: str | Path,
    output_dir: str | Path | None = None,
    markdown: bool = True,
    keep_line_breaks: bool = True,
    timeout_hint: Optional[int] = None,
) -> dict[str, Any]:
    """استخرج Markdown + JSON (بإحداثيات) من PDF عبر OpenDataLoader.

    يعيد dict: {"ok": bool, "markdown": str|None, "json": dict|None,
    "outputs": [مسارات الملفات الناتجة], "processing_time": float,
    "engine": "opendataloader-pdf", "error": str|None}

    timeout_hint: للاستخدام المستقبلي (الغلاف الحالي لا يدعم timeout مباشرة).
    """
    start = time.perf_counter()
    path = Path(pdf_path)
    base: dict[str, Any] = {
        "ok": False,
        "markdown": None,
        "json": None,
        "outputs": [],
        "processing_time": 0.0,
        "engine": "opendataloader-pdf",
        "error": None,
    }
    if not path.is_file():
        base["error"] = f"file not found: {path}"
        return base
    if not is_available():
        base["error"] = (
            "opendataloader-pdf غير مثبت أو java غير موجود "
            "(pip install opendataloader-pdf + JVM)"
        )
        return base

    try:
        import tempfile

        from opendataloader_pdf import run

        out_dir = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="odl_"))
        out_dir.mkdir(parents=True, exist_ok=True)
        run(
            str(path),
            output_folder=str(out_dir),
            generate_markdown=markdown,
            keep_line_breaks=keep_line_breaks,
        )

        outputs = sorted(p for p in out_dir.iterdir() if p.is_file())
        md_text = None
        json_obj = None
        for p in outputs:
            if p.suffix.lower() == ".md" and markdown:
                md_text = p.read_text(encoding="utf-8", errors="replace")
            elif p.suffix.lower() == ".json":
                try:
                    json_obj = json.loads(p.read_text(encoding="utf-8", errors="replace"))
                except json.JSONDecodeError:
                    json_obj = None

        base.update(
            ok=bool(md_text or json_obj),
            markdown=md_text,
            json=json_obj,
            outputs=[str(p) for p in outputs],
            processing_time=time.perf_counter() - start,
        )
        if not base["ok"]:
            base["error"] = "no markdown/json output produced"
        return base
    except Exception as exc:  # سياسة: الفشل يُبلَّغ ولا يُرفع
        base["error"] = f"{type(exc).__name__}: {exc}"
        base["processing_time"] = time.perf_counter() - start
        return base

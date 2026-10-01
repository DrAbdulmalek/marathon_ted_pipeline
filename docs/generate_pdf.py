"""
توليد PDF من USER_MANUAL.md باستخدام WeasyPrint.
يدعم الاتجاه من اليمين لليسار للعربية.
"""
import logging
import re
from pathlib import Path

import markdown
from weasyprint import HTML, CSS

logger = logging.getLogger(__name__)

SRC = Path("docs/USER_MANUAL.md")
OUT_PDF = Path("docs/USER_MANUAL.pdf")
OUT_HTML = Path("docs/USER_MANUAL.html")

CSS_STYLE = """
@page {
    size: A4;
    margin: 2cm 1.5cm;
    @bottom-center {
        content: "صفحة " counter(page) " من " counter(pages);
        font-family: 'Cairo', sans-serif;
        font-size: 9pt;
        color: #666;
    }
}
@page :first {
    @bottom-center { content: ""; }
}

body {
    font-family: 'Cairo', 'DejaVu Sans', sans-serif;
    direction: rtl;
    text-align: right;
    line-height: 1.7;
    color: #222;
    font-size: 11pt;
}

h1 { color: #1e40af; font-size: 24pt; border-bottom: 3px solid #3b82f6; padding-bottom: 6px; }
h2 { color: #1e3a8a; font-size: 18pt; margin-top: 24px; border-right: 4px solid #3b82f6; padding-right: 12px; }
h3 { color: #1e40af; font-size: 14pt; margin-top: 18px; }
h4 { color: #374151; font-size: 12pt; }

code {
    font-family: 'DejaVu Sans Mono', monospace;
    background: #f3f4f6;
    padding: 2px 6px;
    border-radius: 3px;
    direction: ltr;
    display: inline-block;
    color: #dc2626;
}

pre {
    background: #1f2937;
    color: #f9fafb;
    padding: 12px;
    border-radius: 6px;
    direction: ltr;
    text-align: left;
    overflow-x: auto;
    font-size: 9pt;
    line-height: 1.4;
}

pre code {
    background: none;
    color: inherit;
    padding: 0;
}

table {
    width: 100%;
    border-collapse: collapse;
    margin: 12px 0;
    font-size: 10pt;
}

th {
    background: #3b82f6;
    color: white;
    padding: 8px;
    text-align: right;
}

td {
    padding: 6px 8px;
    border-bottom: 1px solid #e5e7eb;
    text-align: right;
}

tr:nth-child(even) td { background: #f9fafb; }

blockquote {
    border-right: 4px solid #f59e0b;
    background: #fffbeb;
    padding: 8px 16px;
    margin: 12px 0;
    color: #78350f;
}

ul, ol { padding-right: 24px; }

hr {
    border: none;
    border-top: 2px dashed #d1d5db;
    margin: 24px 0;
}

.cover {
    text-align: center;
    padding: 100px 0;
    page-break-after: always;
}

.cover h1 {
    font-size: 36pt;
    border: none;
    color: #1e40af;
    margin-bottom: 20px;
}

.cover p {
    font-size: 14pt;
    color: #6b7280;
}
"""


def md_to_html(md_text: str) -> str:
    """تحويل Markdown إلى HTML مع دعم الجداول والأكواد."""
    extensions = [
        "extra",
        "tables",
        "fenced_code",
        "codehilite",
        "toc",
        "sane_lists",
    ]
    return markdown.markdown(md_text, extensions=extensions)


def build_pdf():
    md_text = SRC.read_text(encoding="utf-8")

    # صفحة الغلاف
    cover = """
    <div class="cover">
        <h1>Marathon TED Pipeline</h1>
        <p>دليل المستخدم الكامل</p>
        <p style="font-size: 11pt; margin-top: 40px;">الإصدار 1.0.0</p>
    </div>
    """

    html_body = md_to_html(md_text)
    full_html = f"""<!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <title>Marathon TED Pipeline — دليل المستخدم</title>
    </head>
    <body>
        {cover}
        {html_body}
    </body>
    </html>
    """

    OUT_HTML.write_text(full_html, encoding="utf-8")

    logger.info("توليد PDF...")
    HTML(string=full_html, base_url=".").write_pdf(
        str(OUT_PDF), stylesheets=[CSS(string=CSS_STYLE)]
    )
    logger.info("✅ تم: %s (%.1f KB)",
                OUT_PDF, OUT_PDF.stat().st_size / 1024)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    build_pdf()

from src.epub_ocr import EpubOCRProcessor


def test_epub_preserves_table_rows_and_columns():
    processor = EpubOCRProcessor()
    html = b"""
    <html><body>
      <table>
        <tr><th>Correct</th><th>Incorrect</th></tr>
        <tr><td>ترجمة صحيحة</td><td>ترجمة خاطئة</td></tr>
      </table>
    </body></html>
    """
    out = processor._extract_html_text(html)
    assert "| Correct | Incorrect |" in out
    assert "| ترجمة صحيحة | ترجمة خاطئة |" in out
    assert "| --- | --- |" in out

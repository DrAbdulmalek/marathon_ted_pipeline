# dashboard.py
"""
لوحة التحكم — Streamlit:
- إحصاءات القناة والمعالجة
- معالجة PDF/EPUB تفاعلية
- جلب وترجمة TED
- عارض قواعد OCR
- شريط اللغات المدعومة (10 لغات RTL/LTR)
"""
import json
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
import yaml

st.set_page_config(
    page_title="Marathon TED Pipeline",
    page_icon="🏃",
    layout="wide",
)

# ---------- التهيئة ----------
# dashboard.py في جذر المستودع → parent واحدة تصل الجذر (لا parent.parent كباقي src/*)
# تجاوز النشر: متغير البيئة MARATHON_CONFIG
CONFIG_PATH = Path(
    os.getenv("MARATHON_CONFIG")
    or Path(__file__).resolve().parent / "config" / "config.yaml"
)
with open(CONFIG_PATH, encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)

st.title("🏃 Marathon TED Pipeline")
st.caption("استخراج وترجمة ونشر المحتوى — TED / PDF / EPUB / ASR")

# في dashboard.py
st.sidebar.subheader("🌐 اللغات المدعومة")
from src.languages import get_registry  # noqa: E402

reg = get_registry()
langs = reg.list_all()
selected_lang = st.sidebar.selectbox(
    "اللغة الهدف",
    options=langs,
    format_func=lambda c: f"{reg.get(c)['name']} ({c})",
    index=langs.index("ar") if "ar" in langs else 0,
)

st.sidebar.caption(f"RTL: {'✅' if reg.is_rtl(selected_lang) else '❌'}")
st.sidebar.caption(
    f"المحركات: {', '.join(reg.get(selected_lang).get('models', {}).keys())}"
)

st.sidebar.divider()
st.sidebar.subheader("⚙️ الحالة")
st.sidebar.metric("المحرك الترجمي", CONFIG.get("translation", {}).get("engine", "-"))
st.sidebar.metric("قواعد OCR", "18 قاعدة")
st.sidebar.metric("قناة المصدر", CONFIG.get("telegram", {}).get("source_channel", "-"))


# ---------- التبويبات ----------
tab_stats, tab_ocr, tab_ted, tab_rules = st.tabs(
    ["📊 الإحصاءات", "📄 معالجة مستندات", "🎬 TED", "📏 قواعد OCR"]
)

# ---------- الإحصاءات ----------
with tab_stats:
    downloads = Path(CONFIG["storage"].get("download_dir", "data/downloads"))
    md_files = list(downloads.rglob("*.md")) if downloads.exists() else []
    wrong_files = list(downloads.rglob("*.wrong.md")) if downloads.exists() else []

    c1, c2, c3 = st.columns(3)
    c1.metric("ملفات ناتجة", len(md_files))
    c2.metric("ملفات خاطئة (مفصولة)", len(wrong_files))
    c3.metric("معدل الصحة", f"{100 * (1 - len(wrong_files) / max(len(md_files), 1)):.0f}%")

    if md_files:
        by_day = {}
        for p in md_files:
            day = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d")
            by_day[day] = by_day.get(day, 0) + 1
        df = pd.DataFrame(
            sorted(by_day.items()), columns=["اليوم", "الملفات"]
        )
        fig = px.bar(df, x="اليوم", y="الملفات", title="الإنتاج اليومي")
        st.plotly_chart(fig, use_container_width=True)

# ---------- معالجة المستندات ----------
with tab_ocr:
    st.subheader("📄 معالجة PDF / EPUB")
    up = st.file_uploader("ارفع ملفًا", type=["pdf", "epub"])
    if up is not None and st.button("▶️ ابدأ المعالجة"):
        save_dir = Path(CONFIG["storage"]["download_dir"]) / "dashboard_uploads"
        save_dir.mkdir(parents=True, exist_ok=True)
        save_path = save_dir / f"{datetime.now():%Y%m%d_%H%M%S}_{up.name}"
        save_path.write_bytes(up.getvalue())

        with st.spinner("جارٍ المعالجة بقواعد OCR الـ 18..."):
            try:
                if save_path.suffix.lower() == ".pdf":
                    from src.pdf_ocr import PDFOCRProcessor

                    result = PDFOCRProcessor(
                        rules_file=CONFIG["ocr"]["rules_file"],
                        output_dir=save_dir,
                    ).process_and_save(save_path)
                else:
                    from src.epub_ocr import EpubOCRProcessor

                    result = EpubOCRProcessor(
                        rules_file=CONFIG["ocr"]["rules_file"],
                        output_dir=save_dir,
                    ).process_and_save(save_path)

                meta = result["metadata"]
                c1, c2, c3 = st.columns(3)
                c1.metric("التصنيف", "✅ صحيح" if meta["classification"] == "correct" else "⚠️ خاطئ")
                c2.metric("نسبة السلامة", f"{meta['word_ratio'] * 100:.0f}%")
                c3.metric("رموز مرصودة", len(meta["markers"]))
                st.markdown(result["markdown"][:5000])
            except Exception as exc:
                st.error(f"فشلت المعالجة: {exc}")

# ---------- TED ----------
with tab_ted:
    st.subheader("🎬 جلب محادثة TED")
    ted_url = st.text_input("رابط المحادثة", "https://www.ted.com/talks/...")
    do_translate = st.checkbox("ترجمة تلقائية إن غابت الترجمة الرسمية", value=True)
    if st.button("🚀 جلب") and ted_url:
        with st.spinner("جارٍ الجلب..."):
            try:
                from src.ted_fetcher import TedFetcher

                t = TedFetcher(CONFIG)
                transcript = t.fetch(ted_url, target_lang=selected_lang)
                if transcript:
                    st.success(transcript.title)
                    st.text_area("النص الأصلي", transcript.source_text[:4000], height=200)
                    if transcript.target_text:
                        st.text_area("الترجمة", transcript.target_text[:4000], height=200)
                    elif do_translate:
                        from src.translator import Translator

                        res = Translator(engine="google").translate(
                            transcript.source_text, src="en", tgt=selected_lang
                        )
                        st.text_area("ترجمة آلية", res.translated_text[:4000], height=200)
                else:
                    st.error("فشل الجلب — جرّب لاحقًا")
            except Exception as exc:
                st.error(str(exc))

# ---------- القواعد ----------
with tab_rules:
    st.subheader("📏 قواعد OCR الـ 18")
    try:
        with open(CONFIG["ocr"]["rules_file"], encoding="utf-8") as f:
            rules = yaml.safe_load(f)
        rows = [
            {
                "الرقم": r["id"],
                "الاسم": r["name"],
                "الفئة": r["category"],
                "الوصف": r["description"],
                "مفعّلة": "✅" if r.get("enabled") else "❌",
            }
            for r in rules["rules"]
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
    except Exception as exc:
        st.error(f"تعذر تحميل القواعد: {exc}")

"""
بوت تيليجرام للتحكم:
- /start : ترحيب
- /help : قائمة الأوامر
- /status : حالة النظام
- /queue : حالة queue
- /jobs : آخر المهام
- /rules : قواعد OCR الحالية
- /translate <نص> : ترجمة فورية
- /fetch <url> : جلب ترجمة TED
- رفع ملف PDF/EPUB → معالجة وإرجاع النتيجة
- /key : إدارة API Keys (للمدير)
"""
import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path

import yaml
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes,
)
from telegram.constants import ParseMode

from .queue_worker import enqueue_pdf, enqueue_epub, enqueue_ted, get_job_status
from .translator import Translator
from .auth import verify_api_key, create_api_key

logger = logging.getLogger(__name__)


class MarathonBot:
    def __init__(self, config_path: str = "config/config.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not self.token:
            raise ValueError("TELEGRAM_BOT_TOKEN مطلوب")

        # المستخدمون المصرح لهم (chat_id)
        self.admins = set(
            int(x) for x in os.getenv("BOT_ADMINS", "").split(",") if x.strip()
        )

        self.translator = Translator(engine="google")

        self.app = Application.builder().token(self.token).build()
        self._register_handlers()

    # ---------- الصلاحيات ----------
    def _is_admin(self, update: Update) -> bool:
        return update.effective_chat.id in self.admins

    # ---------- الأوامر ----------
    async def cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            f"👋 مرحبًا بك في *Marathon Bot*\n\n"
            f"أنا مساعدك للتحكم بنظام الماراثون.\n"
            f"استخدم /help لقائمة الأوامر.",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def cmd_help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        text = (
            "*الأوامر المتاحة:*\n\n"
            "*عامة:*\n"
            "• /start — ترحيب\n"
            "• /help — هذه القائمة\n"
            "• /status — حالة النظام\n"
            "• /queue — حالة الـ queue\n"
            "• /jobs — آخر المهام\n"
            "• /rules — قواعد OCR\n\n"
            "*الترجمة:*\n"
            "• `/translate <نص>` — ترجمة فورية\n"
            "• `/fetch <TED_URL>` — جلب ترجمة TED\n\n"
            "*معالجة الملفات:*\n"
            "• أرسل PDF أو EPUB → تتم المعالجة تلقائيًا\n\n"
            "*المدير فقط:*\n"
            "• `/key <name>` — إنشاء API Key جديد\n"
            "• `/stats` — إحصائيات تفصيلية"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def cmd_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        from .queue_worker import task_queue
        from .metrics import update_queue_metrics, QUEUE_JOBS

        update_queue_metrics()

        text = (
            "📊 *حالة النظام*\n\n"
            f"🕐 الوقت: `{datetime.now():%Y-%m-%d %H:%M:%S}`\n"
            f"📥 Queue: `{len(task_queue)}` pending\n"
            f"⚙️ Started: `{len(task_queue.started_job_registry)}`\n"
            f"✅ Finished (24h): `{len(task_queue.finished_job_registry)}`\n"
            f"❌ Failed (24h): `{len(task_queue.failed_job_registry)}`\n"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def cmd_queue(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        from .queue_worker import task_queue

        keyboard = [[
            InlineKeyboardButton("🔄 تحديث", callback_data="refresh_queue"),
        ]]
        text = self._queue_text(task_queue)
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    def _queue_text(self, q) -> str:
        return (
            "📋 *حالة الـ Queue*\n\n"
            f"• في الانتظار: `{len(q)}`\n"
            f"• قيد التنفيذ: `{len(q.started_job_registry)}`\n"
            f"• مكتملة: `{len(q.finished_job_registry)}`\n"
            f"• فاشلة: `{len(q.failed_job_registry)}`\n"
            f"• مؤجلة: `{len(q.deferred_job_registry)}`"
        )

    async def refresh_queue_callback(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        from .queue_worker import task_queue
        await query.edit_message_text(
            self._queue_text(task_queue),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 تحديث", callback_data="refresh_queue"),
            ]]),
        )

    async def cmd_rules(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        with open(self.config["ocr"]["rules_file"], encoding="utf-8") as f:
            rules = yaml.safe_load(f)
        vm = rules["visual_markers"]
        text = (
            "📜 *قواعد OCR*\n\n"
            f"• الإصدار: `{rules['version']}`\n"
            f"• علامات الصحيح: `{' '.join(vm['correct'])}`\n"
            f"• علامات الخاطئ: `{' '.join(vm['incorrect'])}`\n"
            f"• الجداول: `{rules['table_rules']['output_format']}`\n"
            f"• المخرجات: `{rules['verification']['final_status_options']}`\n"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def cmd_translate(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not ctx.args:
            await update.message.reply_text("الاستخدام: `/translate <نص>`",
                                             parse_mode=ParseMode.MARKDOWN)
            return

        text = " ".join(ctx.args)
        msg = await update.message.reply_text("⏳ جارٍ الترجمة...")

        try:
            result = self.translator.translate(text, src="auto", tgt="ar")
            await msg.edit_text(
                f"🌐 *الترجمة:*\n\n{result.translated_text}\n\n"
                f"_المحرك: {result.engine}_",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            await msg.edit_text(f"❌ فشل الترجمة: {e}")

    async def cmd_fetch(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not ctx.args:
            await update.message.reply_text("الاستخدام: `/fetch <TED_URL>`",
                                             parse_mode=ParseMode.MARKDOWN)
            return

        url = ctx.args[0]
        msg = await update.message.reply_text("⏳ جلب المحادثة...")

        try:
            job_id = enqueue_ted(url, translate=True, target_lang="ar")
            await msg.edit_text(
                f"✅ *تم جدولة المهمة*\n\n"
                f"🆔 Job: `{job_id}`\n"
                f"استخدم /jobs للمتابعة.",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            await msg.edit_text(f"❌ خطأ: {e}")

    async def cmd_jobs(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        from .queue_worker import task_queue
        jobs = task_queue.get_jobs(offset=0, length=10)
        if not jobs:
            await update.message.reply_text("لا توجد مهام.")
            return

        lines = ["📋 *آخر المهام:*\n"]
        for j in jobs:
            status_emoji = {
                "queued": "🕐", "started": "⚙️",
                "finished": "✅", "failed": "❌",
                "deferred": "⏸",
            }.get(j.get_status(), "❓")
            lines.append(
                f"{status_emoji} `{j.id[:8]}...` — {j.get_status()}\n"
                f"   func: `{j.func_name}`"
            )
        await update.message.reply_text(
            "\n".join(lines), parse_mode=ParseMode.MARKDOWN
        )

    async def cmd_key(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._is_admin(update):
            await update.message.reply_text("⛔ صلاحيات المدير مطلوبة.")
            return
        if not ctx.args:
            await update.message.reply_text("الاستخدام: `/key <name>`",
                                             parse_mode=ParseMode.MARKDOWN)
            return
        name = " ".join(ctx.args)
        key = create_api_key(name, role="user")
        await update.message.reply_text(
            f"🔑 *API Key جديد*\n\n"
            f"الاسم: `{name}`\n"
            f"المفتاح:\n`{key}`\n\n"
            f"⚠️ احفظه الآن — لن يظهر مجددًا.",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def cmd_stats(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._is_admin(update):
            await update.message.reply_text("⛔ صلاحيات المدير مطلوبة.")
            return
        from .queue_worker import task_queue
        text = (
            "📈 *إحصائيات تفصيلية*\n\n"
            f"• Queue pending: `{len(task_queue)}`\n"
            f"• Finished: `{len(task_queue.finished_job_registry)}`\n"
            f"• Failed: `{len(task_queue.failed_job_registry)}`\n"
            f"• Grafana: https://marathon.yourdomain.com/grafana\n"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    # ---------- معالجة الملفات ----------
    async def handle_document(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        doc = update.message.document
        if not doc:
            return

        name = doc.file_name or "file"
        ext = Path(name).suffix.lower()

        if ext not in (".pdf", ".epub"):
            await update.message.reply_text(
                f"⚠️ نوع الملف غير مدعوم: `{ext}`\n"
                f"المدعوم: PDF, EPUB",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        msg = await update.message.reply_text(
            f"📥 استلمت `{name}`\n"
            f"جاري التنزيل...",
            parse_mode=ParseMode.MARKDOWN,
        )

        try:
            # تنزيل الملف
            file = await doc.get_file()
            upload_dir = Path(self.config["storage"]["download_dir"]) / "bot_uploads"
            upload_dir.mkdir(parents=True, exist_ok=True)
            save_path = upload_dir / f"{datetime.now():%Y%m%d_%H%M%S}_{name}"
            await file.download_to_drive(str(save_path))

            # جدولة
            if ext == ".pdf":
                job_id = enqueue_pdf(
                    str(save_path),
                    str(Path(self.config["storage"]["download_dir"]) / "api_pdf"),
                    self.config["ocr"]["rules_file"],
                )
            else:
                job_id = enqueue_epub(
                    str(save_path),
                    str(Path(self.config["storage"]["download_dir"]) / "api_epub"),
                    self.config["ocr"]["rules_file"],
                )

            await msg.edit_text(
                f"✅ *تم استلام الملف*\n\n"
                f"📄 `{name}`\n"
                f"🆔 Job: `{job_id}`\n\n"
                f"سيتم إعلامك عند الانتهاء.",
                parse_mode=ParseMode.MARKDOWN,
            )

            # متابعة الـ job في الخلفية
            asyncio.create_task(
                self._watch_job(ctx, update.effective_chat.id, job_id, name)
            )

        except Exception as e:
            logger.exception("فشل استقبال الملف")
            await msg.edit_text(f"❌ خطأ: {e}")

    async def _watch_job(self, ctx, chat_id: int, job_id: str, name: str):
        """مراقبة job حتى الانتهاء وإعلام المستخدم."""
        for _ in range(180):   # 15 دقيقة
            await asyncio.sleep(5)
            status = get_job_status(job_id)
            st = status["status"]
            if st == "finished":
                result = status.get("result", {})
                md_path = result.get("markdown_path", "")
                meta_path = result.get("metadata_path", "")
                caption = (
                    f"✅ *اكتملت المعالجة*\n\n"
                    f"📄 `{name}`\n"
                    f"🏷️ التصنيف: `{', '.join(result.get('metadata', {}).get('labels', []))}`\n"
                    f"🎯 الثقة: `{result.get('metadata', {}).get('confidence', 'low')}`"
                )
                await ctx.bot.send_message(chat_id, caption,
                                            parse_mode=ParseMode.MARKDOWN)
                if md_path and Path(md_path).exists():
                    await ctx.bot.send_document(
                        chat_id, document=open(md_path, "rb"),
                        filename=Path(md_path).name,
                    )
                if meta_path and Path(meta_path).exists():
                    await ctx.bot.send_document(
                        chat_id, document=open(meta_path, "rb"),
                        filename=Path(meta_path).name,
                    )
                return

            elif st == "failed":
                err = status.get("error", "خطأ غير معروف")
                await ctx.bot.send_message(
                    chat_id,
                    f"❌ *فشلت المعالجة*\n\n`{name}`\n\n`{err}`",
                    parse_mode=ParseMode.MARKDOWN,
                )
                return

        await ctx.bot.send_message(
            chat_id, f"⏰ انتهت المهلة لـ `{name}`",
            parse_mode=ParseMode.MARKDOWN,
        )

    # ---------- التسجيل ----------
    def _register_handlers(self):
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("help", self.cmd_help))
        self.app.add_handler(CommandHandler("status", self.cmd_status))
        self.app.add_handler(CommandHandler("queue", self.cmd_queue))
        self.app.add_handler(CommandHandler("jobs", self.cmd_jobs))
        self.app.add_handler(CommandHandler("rules", self.cmd_rules))
        self.app.add_handler(CommandHandler("translate", self.cmd_translate))
        self.app.add_handler(CommandHandler("fetch", self.cmd_fetch))
        self.app.add_handler(CommandHandler("key", self.cmd_key))
        self.app.add_handler(CommandHandler("stats", self.cmd_stats))
        self.app.add_handler(CommandHandler("langs", self.cmd_langs))
        self.app.add_handler(CommandHandler("translate_to", self.cmd_translate_to))
        self.app.add_handler(MessageHandler(
            filters.Document.ALL, self.handle_document,
        ))
        self.app.add_handler(MessageHandler(
            filters.VOICE | filters.AUDIO | filters.VIDEO, self.handle_voice,
        ))
        self.app.add_handler(CallbackQueryHandler(
            self.refresh_queue_callback, pattern="^refresh_queue$",
        ))

    async def cmd_langs(self, update, ctx):
        """عرض اللغات المتاحة."""
        from .languages import get_registry
        reg = get_registry()
        lines = ["🌐 *اللغات المتاحة:*\n"]
        for code, info in reg.data.items():
            engines = ", ".join(info.get("models", {}).keys())
            rtl = " (RTL)" if info["rtl"] else ""
            lines.append(f"• `{code}` — {info['name']}{rtl}")
            lines.append(f"   محركات: _{engines}_")
        await update.message.reply_text(
            "\n".join(lines), parse_mode=ParseMode.MARKDOWN
        )

    async def cmd_translate_to(self, update, ctx):
        """`/translate_to ar,fr Hello` — ترجمة لعدة لغات."""
        if len(ctx.args) < 2:
            await update.message.reply_text(
                "الاستخدام: `/translate_to ar,fr <نص>`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        langs = ctx.args[0].split(",")
        text = " ".join(ctx.args[1:])

        from .translator import MultiLangTranslator
        multi = MultiLangTranslator(engine="google")

        msg = await update.message.reply_text("⏳ جارٍ الترجمة...")
        lines = []
        for lc in langs:
            try:
                r = multi.translate(text, tgt=lc)
                lines.append(f"*{lc}*: {r.translated_text}")
            except Exception as e:
                lines.append(f"*{lc}*: ❌ {e}")

        await msg.edit_text("\n\n".join(lines), parse_mode=ParseMode.MARKDOWN)

    async def handle_voice(self, update, ctx):
        """معالجة رسالة صوتية أو فيديو."""
        msg = update.message
        media = msg.voice or msg.audio or msg.video
        if not media:
            return

        m = await msg.reply_text("🎙️ جارٍ التنزيل...")

        file = await media.get_file()
        name = (
            getattr(msg.voice, "file_unique_id", None)
            or getattr(msg.audio, "file_name", None)
            or f"voice_{msg.message_id}"
        )
        if not name.endswith((".mp3", ".wav", ".ogg", ".mp4", ".m4a")):
            name += ".ogg"

        upload_dir = Path(self.config["storage"]["download_dir"]) / "bot_asr"
        upload_dir.mkdir(parents=True, exist_ok=True)
        save_path = upload_dir / name
        await file.download_to_drive(str(save_path))

        await m.edit_text("🧠 جارٍ النسخ والترجمة...")

        try:
            from .asr.pipeline import transcribe_and_translate
            result = transcribe_and_translate(
                audio_path=str(save_path),
                source_lang="en",
                target_lang="ar",
            )

            await m.edit_text(
                f"✅ *اكتمل*\n\n"
                f"⏱️ المدة: `{result['duration']:.1f}s`\n"
                f"📝 المقاطع: `{result['segments_count']}`",
                parse_mode=ParseMode.MARKDOWN,
            )

            # أرسل الملفات
            for key in ("srt_bilingual", "translation_txt", "json"):
                fp = Path(result[key])
                if fp.exists():
                    with open(fp, "rb") as fh:
                        await msg.reply_document(
                            document=fh,
                            filename=fp.name,
                        )
        except Exception as e:
            logger.exception("فشل ASR")
            await m.edit_text(f"❌ فشل: {e}")

    def run(self):
        logger.info("🤖 بدء تشغيل البوت...")
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    bot = MarathonBot("config/config.yaml")
    bot.run()


if __name__ == "__main__":
    main()

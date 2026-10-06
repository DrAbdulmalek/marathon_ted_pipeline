# src/channel_monitor.py
"""Incremental, idempotent Telegram source-channel monitor."""
import asyncio, logging, os, re
from pathlib import Path
import yaml
from .telegram_ingestion_state import TelegramIngestionState
logger=logging.getLogger(__name__)
TED_URL_RE=re.compile(r"https?://(?:www\.)?ted\.com/talks/\S+")
class ChannelMonitor:
    def __init__(self,config_path="config/config.yaml"):
        with open(config_path,encoding="utf-8") as f:self.config=yaml.safe_load(f) or {}
        tg=self.config.get("telegram",{}); configured=tg.get("source_channels")
        if configured is None: configured=[tg.get("source_channel","")]
        self.sources=[str(x).strip() for x in configured if str(x).strip()]
        if not self.sources: raise ValueError("telegram.source_channel(s) مطلوب")
        self.download_dir=Path(self.config.get("storage",{}).get("download_dir","data/downloads"))
        self.rules_file=self.config.get("ocr",{}).get("rules_file","config/marathon_ocr_rules.yaml")
        self.state=TelegramIngestionState(tg.get("ingestion_state","data/telegram_ingestion.sqlite3"))
        self.initial_sync=tg.get("initial_sync","latest")
        if self.initial_sync not in ("latest","from_start"): raise ValueError("telegram.initial_sync يجب أن يكون latest أو from_start")
        self._client=None; self.running=False
    def _get_client(self):
        if self._client is None:
            from telethon import TelegramClient
            self._client=TelegramClient(os.getenv("TELEGRAM_SESSION","marathon_session"),int(os.getenv("TELEGRAM_API_ID",0)),os.getenv("TELEGRAM_API_HASH",""))
        return self._client
    def handle_document(self,event):
        from .pdf_ocr import PDFOCRProcessor
        from .epub_ocr import EpubOCRProcessor
        from .telegram_uploader import TelegramUploader
        doc=event.message.document; attrs=getattr(doc,"attributes",[])
        filename=next((a.file_name for a in attrs if getattr(a,"file_name",None)),f"doc_{event.message.id}")
        suffix=Path(filename).suffix.lower()
        if suffix not in (".pdf",".epub"): return
        self.download_dir.mkdir(parents=True,exist_ok=True); save_path=self.download_dir/filename
        event.message.download_media(file=str(save_path))
        if suffix==".pdf": result=PDFOCRProcessor(rules_file=self.rules_file,output_dir=self.download_dir/"pdf").process_and_save(save_path)
        else: result=EpubOCRProcessor(rules_file=self.rules_file,output_dir=self.download_dir/"epub").process_and_save(save_path)
        title=result["metadata"].get("source_file",filename)
        n=TelegramUploader(self.config).upload_results(self.download_dir/Path(filename).stem,title=title)
        logger.info("رُفع %s ملفًا نتيجةً لـ %s",n,filename)
    def handle_ted_link(self,event,url):
        from .ted_fetcher import TedFetcher
        from .telegram_uploader import TelegramUploader
        transcript=TedFetcher(self.config).fetch(url)
        if not transcript:return
        text=f"🎬 {transcript.title}\n\n{transcript.target_text or transcript.source_text}"
        if not TelegramUploader(self.config).send_message(text): raise RuntimeError("فشل نشر نتيجة TED")
    def handle_text(self,event):
        from .translator import Translator
        text=(event.message.message or "").strip()
        if not text or TED_URL_RE.search(text) or not (2<len(text)<4000): return
        t=Translator(engine="google")
        res=t.translate(text,src="ar",tgt="en") if re.search(r"[\u0600-\u06ff]",text) else t.translate(text,src="en",tgt="ar")
        if not event.reply(res.translated_text): raise RuntimeError("فشل الرد على رسالة المصدر")
    async def _process_message(self,source_id,message):
        if not message or not getattr(message,"id",None): return False
        message_id=int(message.id)
        if not self.state.claim(source_id,message_id): return False
        try:
            event=type("Event",(),{"message":message})()
            if message.document:self.handle_document(event)
            elif message.message:
                match=TED_URL_RE.search(message.message)
                self.handle_ted_link(event,match.group(0)) if match else self.handle_text(event)
            self.state.mark_done(source_id,message_id); return True
        except Exception:
            self.state.release(source_id,message_id); raise
    async def _bootstrap_source(self,client,entity):
        source_id=str(entity.id)
        if self.state.get_cursor(source_id)!=0 or self.initial_sync=="from_start": return
        latest=await client.get_messages(entity,limit=1)
        if latest and latest[0]:
            self.state.set_cursor(source_id,int(latest[0].id))
            logger.info("تهيئة %s عند الرسالة الحالية %s؛ لن يُعاد التاريخ القديم",source_id,latest[0].id)
    async def _catch_up_source(self,client,entity):
        source_id=str(entity.id); cursor=self.state.get_cursor(source_id)
        async for message in client.iter_messages(entity,min_id=cursor,reverse=True):
            try: await self._process_message(source_id,message)
            except Exception:
                logger.exception("توقفت المزامنة عند source=%s message=%s؛ سيُعاد لاحقًا",source_id,getattr(message,"id",None)); break
            self.state.set_cursor(source_id,int(message.id))
    async def _run_async(self):
        from telethon import events
        client=self._get_client(); await client.start()
        entities=[await client.get_entity(source) for source in self.sources]
        async def on_message(event):
            try: await self._process_message(str(event.chat_id),event.message)
            except Exception: logger.exception("فشل processing source=%s message=%s",event.chat_id,event.message.id)
        client.add_event_handler(on_message,events.NewMessage(chats=entities))
        for entity in entities: await self._bootstrap_source(client,entity)
        for entity in entities: await self._catch_up_source(client,entity)
        self.running=True; logger.info("المراقبة التزايدية بدأت: %s",", ".join(self.sources))
        await client.run_until_disconnected()
    def run(self):
        try: asyncio.get_event_loop().run_until_complete(self._run_async())
        except RuntimeError: asyncio.run(self._run_async())
    def stop(self):
        self.running=False
        if self._client: asyncio.ensure_future(self._client.disconnect())

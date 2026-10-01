# المخطط المعماري — Marathon TED Pipeline

```mermaid
graph TB
    subgraph External["🌐 المصادر الخارجية"]
        TG_SRC[قناة تيليجرام<br/>المصدر]
        TED[TED Talks]
        AUDIO[ملفات صوت/فيديو]
        DOCS[PDF/EPUB/صور]
    end

    subgraph Users["👥 المستخدمون"]
        WEB[متصفح<br/>Dashboard]
        BOT_USER[Telegram Bot]
        API_CLIENT[عملاء API]
    end

    subgraph Gateway["🚪 البوابة"]
        NGINX[Nginx + SSL<br/>Rate Limit]
    end

    subgraph Core["⚙️ الخدمات الأساسية"]
        API[FastAPI<br/>+ Auth + Webhooks]
        BOT[Telegram Bot]
        DASH[Streamlit<br/>Dashboard]
        MONITOR[Channel<br/>Monitor]
    end

    subgraph Processing["🔬 المعالجة"]
        QUEUE[(Redis Queue)]
        WORKER[RQ Workers<br/>x N]
        PDF[PDF/EPUB<br/>OCR]
        ASR[Whisper<br/>ASR]
        TRANS[Translators<br/>Google/DeepL/HF]
        QUALITY[Quality<br/>Evaluator]
    end

    subgraph Storage["💾 التخزين"]
        PG[(PostgreSQL)]
        REDIS[(Redis)]
        FS[Filesystem<br/>PDF/MD/SRT]
        SQLITE[(SQLite<br/>Auth/AB/Quality)]
    end

    subgraph Output["📤 المخرجات"]
        TG_TGT[قناة تيليجرام<br/>الهدف]
        CMS[WordPress /<br/>Notion / Webhook]
        DOWNLOAD[تنزيل<br/>SRT/TXT/MD]
    end

    subgraph Observability["📊 المراقبة"]
        PROM[Prometheus]
        GRAF[Grafana]
        ALERT[Alertmanager]
    end

    TG_SRC --> MONITOR
    TED --> API
    AUDIO --> API
    DOCS --> API
    DOCS --> MONITOR

    WEB --> NGINX
    BOT_USER --> BOT
    API_CLIENT --> NGINX

    NGINX --> API
    NGINX --> DASH

    API --> QUEUE
    BOT --> QUEUE
    MONITOR --> QUEUE
    MONITOR --> TG_TGT

    QUEUE --> WORKER
    WORKER --> PDF
    WORKER --> ASR
    WORKER --> TRANS
    WORKER --> QUALITY

    PDF --> FS
    ASR --> FS
    TRANS --> CMS
    QUALITY --> SQLITE

    API --> PG
    WORKER --> PG
    API --> REDIS
    WORKER --> REDIS

    API --> PROM
    WORKER --> PROM
    PROM --> GRAF
    PROM --> ALERT
    ALERT --> BOT_USER

    style API fill:#3b82f6,color:#fff
    style BOT fill:#3b82f6,color:#fff
    style QUEUE fill:#ef4444,color:#fff
    style WORKER fill:#ef4444,color:#fff
    style PROM fill:#22c55e,color:#fff
```

مخطط تسلسلي: رفع PDF من البوت

```mermaid
sequenceDiagram
    actor U as المستخدم
    participant B as Bot
    participant A as API
    participant Q as Redis Queue
    participant W as Worker
    participant O as OCR Engine
    participant S as Storage
    participant H as Webhooks

    U->>B: يرفع PDF
    B->>B: تنزيل الملف
    B->>Q: enqueue_pdf()
    Q-->>B: job_id
    B-->>U: ✅ Job queued

    W->>Q: fetch job
    Q-->>W: payload
    W->>O: process()
    O-->>W: markdown + metadata
    W->>S: حفظ MD + JSON
    W->>H: fire_event("job.completed")
    W->>Q: set result

    loop كل 5s
        B->>Q: get_status(job_id)
        Q-->>B: status
    end
    B-->>U: ✅ Files + Metadata
```

مخطط معمارية النشر على Kubernetes

```mermaid
graph LR
    subgraph Internet
        USER[المستخدم]
    end

    subgraph K8s["☸️ Kubernetes Cluster"]
        ING[Ingress<br/>nginx]
        subgraph NS["namespace: marathon"]
            API_POD[API Pods x3<br/>HPA: 2-10]
            WRK_POD[Worker Pods x4<br/>HPA: 2-20]
            BOT_POD[Bot Pod x1]
            MON_POD[Monitor Pod x1]
            PG_POD[(Postgres<br/>StatefulSet)]
            RD_POD[(Redis)]
            PVC[(PVC<br/>50Gi)]
        end
    end

    subgraph Monitor["📊 مراقبة"]
        PROM[Prometheus]
        GRAF[Grafana]
    end

    USER --> ING
    ING --> API_POD
    API_POD --> RD_POD
    RD_POD --> WRK_POD
    WRK_POD --> PVC
    API_POD --> PG_POD
    WRK_POD --> PG_POD
    API_POD -.->|metrics| PROM
    WRK_POD -.->|metrics| PROM

# System Intelligence Monitor — SIM

**SIM** مشروع مفتوح المصدر لمراقبة أداء حواسيب Linux وتسجيله وتحليله. الهدف بناء أداة عامة، مع أول اختبارات ميدانية مخططة على Ubuntu 24.04 LTS.

**الوضع (28/10/2026):** نسخة طرفية تجريبية **v0.1.0a1** (ألفا، غير مختبرة بعد على حاسوب المستخدم). نجحت اختبارات أولية في بيئة Linux معزولة؛ ليس لدينا حتى الآن حزمة .deb أو واجهة سطح مكتب. [تفاصيل التنفيذ وحدوده](docs/IMPLEMENTATION_STATUS.md).

## تثبيت النسخة التجريبية على Ubuntu 24.04

لا تثبّت المشروع بصلاحية root. يُنصح ببيئة افتراضية Python:

```bash
sudo apt update
sudo apt install python3-venv python3-pip git
# Clone into a directory of your choice:
git clone https://github.com/scientifica007/System-Intelligence-Monitor-SIM.git
cd System-Intelligence-Monitor-SIM
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
sim doctor --json
```

تحتاج هذه الطريقة إلى الإنترنت أثناء تثبيت الاعتمادات. بعد ذلك، **المراقبة والتسجيل محليان**. يمكن استعمال `./.venv/bin/sim` من أي طرفية حتى دون تفعيل البيئة.

## نسخة الطرفية (أوامر منفذة)

```bash
sim doctor --json
sim start --label "Brave baseline" --interval 2
sim status --json
sim show cpu --json
sim show ram --json
sim show disk --json
sim show network --json
sim show gpu --json
sim top --sort cpu --limit 15
sim top --sort ram --limit 10
sim live --refresh 2       # Ctrl+C closes only the view
sim stop
sim sessions list --json
sim sessions show SESSION_ID --json
sim export SESSION_ID --format jsonl --output ./sim-session.jsonl
sim export SESSION_ID --format json --output ./sim-session.json
```

تعمل خدمة التسجيل في **عملية منفصلة** عن نافذة الطرفية، ويمكن إغلاق النافذة والاستمرار في العمل داخل جلسة تسجيل الدخول الحالية. لا نضمن الاستمرار بعد تسجيل الخروج أو إعادة التشغيل. هذه النسخة تستخدم Python subprocess مع جلسة عمليات مستقلة، **وليس systemd --user بعد**. الإيقاف بأمر `sim stop` يرسل SIGTERM إلى العملية المطابقة لهوية PID وزمن إنشائها، وينتظر إغلاق الملفات. لا يحتفظ النظام بالعمليات الخفية بعد تثبيت البرنامج؛ يبدأ التسجيل فقط بأمرك.

### ملاحظات أساسية

- **لا توجد بعد قياسات فعلية لاستهلاك GPU أو الواط لكل تطبيق.** تظهر حقولها `null` مع سبب عدم الدعم. يقوم `doctor` بجرد أجهزة DRM المقروءة والمستشعرات المتاحة.
- يتم حساب CPU لكل عملية كنسبة من نواة واحدة، وقد تتجاوز 100% للعملية متعددة الخيوط. يبين حقل `cpu_percent_machine` نسبتها من إجمالي الأنوية المنطقية.
- الذاكرة `rss_bytes` ليست مجموعًا دقيقًا لكل التطبيقات بسبب مشاركة الذاكرة.
- `top` يبحث في العمليات المخزنة في آخر عينة، ويقتصر حاليًا على أكبر عدد محدد بالذاكرة عبر `--process-limit` (الافتراضي 300). قد يغيب مستهلك CPU بذاكرة صغيرة إذا تجاوز عدد العمليات الحد.
- أول عينة لا تتضمن معدل CPU أو القرص أو الشبكة لأن قياس المعدل يتطلب عينتين على الأقل. `null` لا تعني صفرًا.
- **لا توجد بعد حدود لحجم التخزين أو سياسة تدوير/احتفاظ آلية.** أوقف التسجيل بعد التجربة وراقب المساحة المتاحة، خاصة قبل تسجيلات طويلة.
- يستخدم SIM أسماء العمليات وPID وRSS وCPU دون تسجيل أوامر التشغيل أو عناوين المواقع أو محتوى الشاشة.
- بيانات الجلسات محفوظة محليًا في `$XDG_DATA_HOME/sim/sessions/` (أو `~/.local/share/sim/sessions/`)، وحالة المسجل في `$XDG_STATE_HOME/sim/` (أو `~/.local/state/sim/`).
- تصدير `jsonl` أو `json` لا يمحو الجلسة الأصلية ولا يستبدل ملفًا موجودًا. راجع البيانات قبل مشاركتها.

## التطوير

```bash
python -m pip install -e . pytest
python -m pytest -q
```

## وثائق المشروع

[الميثاق](docs/PROJECT_CHARTER.md) · [المتطلبات](docs/REQUIREMENTS.md) · [المعمارية](docs/ARCHITECTURE.md) · [عقد البيانات](docs/DATA_CONTRACT.md) · [مواصفة الطرفية](docs/CLI_SPEC.md) · [خارطة الطريق](docs/ROADMAP.md) · [خطة الاختبار الميداني](docs/FIELD_TEST_PLAN.md) · [التنفيذ الراهن](docs/IMPLEMENTATION_STATUS.md) · [القرارات](docs/DECISIONS.md).

**الترخيص:** [MIT](LICENSE). المساهمة مرحب بها في إطار [CONTRIBUTING.md](CONTRIBUTING.md).

---

**English summary:** SIM is an offline-first open-source Linux performance monitor and recorder. The current alpha has a CLI, an opt-in detached recorder, JSON/JSONL sessions, CPU/RAM/process/disk/network samples, and capability detection. A GTK desktop, deeper metrics, systemd integration, analysis and wider distro support are planned, not released.

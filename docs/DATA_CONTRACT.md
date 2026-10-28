# عقد البيانات المفتوحة — SIM

**النسخة المستهدفة:** `schema_version: 1.0.0` (مسودة وليست إصدارًا منفذًا).  
**الهدف:** إعادة القراءة والتحليل آليًا، والمحافظة على الفصل بين القياس والتقدير والتشخيص.

## 1. بنية الجلسة المستهدفة
```text
~/.local/share/sim/
  sim.sqlite3                 # فهرسة واستعلامات محلية (تصميم)
  sessions/
    SESSION_ID/
      manifest.json           # بداية الجلسة والآلة وإعدادات الجمع
      capabilities.json       # المستشعرات المتاحة وحدودها
      samples.jsonl           # عينات زمنية مستقلة، سطر JSON لكل عينة
      events.jsonl            # بدء/إيقاف/أخطاء/تغييرات/فجوات
      summary.json            # ملخص قابل لإعادة البناء
~/.config/sim/config.toml
~/.local/state/sim/           # سجلات تشغيل/أخطاء تقنية
```
تُراعى XDG_DATA_HOME وXDG_CONFIG_HOME وXDG_STATE_HOME حين تضبط. أسماء الملفات وبنية المجلدات عقد تصميم أولي قابل لتثبيت نهائي قبل التنفيذ.

## 2. مثال توضيحي لعينة مصطنعة
```json
{
  "schema_version": "1.0.0",
  "session_id": "example-20261028-001",
  "timestamp_utc": "2026-10-28T18:41:00Z",
  "monotonic_ns": 1023478000000,
  "interval_ms": 2000,
  "system": {
    "cpu_percent_total": 32.0,
    "memory_used_bytes": 3865470566,
    "swap_used_bytes": 0
  },
  "processes": [
    {
      "pid": 4246,
      "start_time_utc": "2026-10-28T18:30:00Z",
      "name": "brave",
      "cpu_percent_one_core": 18.0,
      "rss_bytes": 1027604480
    }
  ],
  "gpu": {
    "utilization_percent": null,
    "availability": "unsupported",
    "source": null
  },
  "power": {
    "watts": null,
    "availability": "unavailable",
    "method": null
  }
}
```
**لا تمثل هذه الأرقام قياسات حقيقية لأي جهاز.**

## 3. قواعد الحقول
- القيم غير المتاحة تكتب `null` مع `availability` مثل `unsupported` أو `permission_denied` أو `temporarily_unavailable` أو `not_collected`.
- وحدة الذاكرة والقرص `bytes`، ومعدل النقل `bytes_per_second`، والطاقة `watts`، ودرجة الحرارة `celsius`، والوقت UTC ISO 8601.
- نسب CPU لا تخلط نسبة العملية من نواة واحدة مع نسبتها من إجمالي المعالج؛ وتوثق مدة حساب المعدل.
- التفريق بين عداد تراكمي وفرق عداد لكل فاصل. عند إعادة تشغيل العداد أو اختلال الفاصل نسجل فجوة بدل معدل سلبي مضلل.
- بيانات العمليات مرتبطة بمفتاح `pid + process_start_time`؛ PID وحده غير كاف.
- نظام الإسناد إلى التطبيقات اختياري ويعلن طريقة المطابقة ومستوى الثقة.
- قياس مباشر أو تقدير أو قيمة مشتقة يجب تمييزها بحقل `measurement_kind` و`source` على مستوى المقاييس المتقدمة.

## 4. التوافق والتوسع
- رقم النسخة يحكم تفسير الحقول، والحقول الجديدة غير الكاسرة يمكن تجاهلها لدى القارئ الأقدم.
- تغييرات المعنى أو الوحدة أو حذف حقول تحتاج نسخة رئيسية جديدة ومحوّلًا موثقًا.
- كل ملف JSONL سطره وحدة صالحة، ويمكن للبرامج التعامل مع ملف جزئي بعد الانقطاع؛ يعزل السطر الأخير الناقص ولا يُعتبر عينة صالحة.
- يُخزن `collector_version`، ونظام التشغيل، ومعرّف المصدر عند الضرورة لإعادة إنتاج الحسابات.

## 5. الخصوصية
قد تكشف أسماء البرامج وأوامر التشغيل ومسارات الملفات عن معلومات شخصية. تُعد بيانات الجلسة محلية خاصة افتراضيًا، مع أذونات مجلد 0700 وملف 0600 حيث أمكن. يجب أن يوفر التصدير المشترك خيار حذف مسارات الملفات وأوامر التشغيل والمعرفات الحساسة، مع معاينة قبل الإرسال. لا يُجمع نص لوحة المفاتيح أو محتوى الشاشة أو الحمولة الشبكية.

## 6. مسؤولية الاستنتاج
التقرير يتضمن `observations` (نتائج محسوبة من العينات) و`hypotheses` (تفسيرات محتملة) و`recommendations` (إجراءات مع دليل ومخاطر وثقة). لا يسمح لعناوين «سبب أكيد» إذا كانت الأدلة ارتباطية فقط.

## v0.1.0a3: optional fields and instrumentation
Sample records preserve `schema_version=1.0.0` and all existing fields, and may additionally contain:
```json
"timing": {
  "collector_duration_ms": 12.4,
  "sampling_lateness_ms": 0.5,
  "previous_write_duration_ms": 1.0
}
```
`previous_write_duration_ms` is for the preceding record, `null` for the first record. Historic a1/a2 records have no `timing` key; summary statistics treat them as unavailable. Events `sampling_delay` and `schedule_overrun` live in `events.jsonl` and never imply missing samples were generated. At shutdown `manifest.json` can have `sampling_delay_events` and `skipped_schedule_deadlines`. `summary` computes interval gaps from monotonic timestamps where present; fallback UTC is less suitable if the wall clock changes. These additions are backward compatible under the project's optional-field rule.

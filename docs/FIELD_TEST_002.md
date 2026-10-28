# التقرير الميداني FT-002 — كشف العتاد بمساعدة SIM Doctor

**التاريخ:** 28/10/2026  
**الجهاز المرجعي:** حاسوب قديم بمعالج Intel Core i3 M370، يستخدم Ubuntu 24.04 LTS بحسب تصريح المستخدم.  
**مصادر الدليل:** ملف `sim-doctor.json` المقدم في المحادثة، ومخرجات `free -h` و`lscpu` المصاحبة. لم يتصل فريق التحليل بالجهاز عن بُعد.  
**الخصوصية:** لا يُودَع ملف JSON الشخصي خامًا في المستودع العام؛ تُنقل خصائص العتاد العامة فقط.

## 1. اتساق الهوية التقنية

| المعلومة | نتيجة القياس أو العرض | وضع التحقق |
|---|---|---|
| معمارية CPU | x86_64 | متطابقة بين doctor وlscpu |
| المعالج | Intel Core i3 M370 @ 2.40GHz | lscpu |
| عدد الأنوية المادية | 2 | doctor وlscpu |
| عدد المعالجات المنطقية | 4 | doctor وlscpu |
| الذاكرة التي يعرضها النظام | 8,110,960,640 bytes = 7.5539 GiB | doctor وfree (7.6Gi مدورة) |
| Swap | 4.0 GiB، المستخدمة 0 B | free |
| kernel | 7.0.0-38-generic | doctor |
| GPU PCI | 8086:0046 | اكتُشف بواسطة /sys/class/drm/card1/device |
| بداية الفحص UTC | 2026-10-28T20:06:37.073Z | ملف doctor |

**تنبيه بشأن RAM:** الذاكرة التي يقدمها Linux ~7.55 GiB، وهي تتسق مع جهاز يحوي ~8 GiB إجماليًا مع حجوزات النظام/العتاد؛ لا توجد بعد أدلة مباشرة على عدد وسعة شرائح DIMM الفعلية. سبق أن وُصفت ذاكرة الحاسوب بأنها شريحتان × 8 GB (16 GB)، وهذا تعارض **غير محسوم** يحتاج فحص SMBIOS. لا نشخّص عطلًا بمجرد اختلاف المصدرين.

**تنبيه بشأن CPU scaling:** `CPU(s) scaling MHz: 59%` في `lscpu` لا يمثل نسبة استهلاك CPU اللحظية؛ هو وصف متعلق بتردد المعالج المتدرج.

## 2. مصفوفة إتاحة SIM Doctor
| Capability | availability | source / التفسير |
|---|---|---|
| CPU, Memory, Swap, Processes | available | psutil/procfs |
| Disk I/O, Network I/O | available | psutil/procfs |
| GPU inventory | available | sysfs، جهاز card1 بمعرّف 8086:0046 |
| GPU per-process | unsupported | "Not implemented; hardware support varies" |
| Power per-process | unsupported | "No reliable per-application watt meter" |
| Temperature | available | psutil/hwmon؛ هذا لا يثبت أن المسجل يحفظ درجات الحرارة |
| Battery | unsupported | "No accessible battery"؛ لا يثبت أن البطارية غير موجودة |
| SMART | unsupported | "SMART probe not implemented" |

## 3. فحص معقولية التصميم
1. الكشف عن المعالج والذاكرة والأجهزة الرسومية نجح فعليًا، ولم تُختلق نسب GPU أو الطاقة.
2. `system.distribution` يساوي `Linux-7.0.0-38-generic-x86_64-with-glibc2.39`، وهي نتيجة `platform.platform()` وليست حقل distro صحيحًا؛ يجب إضافة `/etc/os-release` مع الاحتفاظ ببيانات النواة المنفصلة.
3. `temperature.available` لا يتضمن أسماء المستشعرات أو القيم أو الوحدات؛ الأولوية تصميم طبقة إدراج درجات الحرارة ضمن العينات عند استطاعة الجهاز.
4. البطارية وSMART لا يمكن تصنيفهما عيوبًا عتادية من تقرير `doctor` الحالي؛ تختلف الدلالات بين «الوظيفة غير منفذة» و«الجهاز غير موجود» و«لا صلاحية».
5. GPU `8086:0046` يطابق عائلة الرسوميات Intel Core 2010 Ironlake/Arrandale. إمكانية رصد الاستهلاك لكل عملية تحتاج تحقيقًا منفصلًا في عدادات i915، دون وعد بدعم غير موجود.
6. `lscpu` يعرض `Mds: Vulnerable: Clear CPU buffers attempted, no microcode; SMT vulnerable`. هذه ملاحظة أمنية من النظام، لا تعني تلقائيًا وجود اختراق، وينبغي عدم تغيير kernel أو microcode دون تحقق من تحديثات الشركة/التوزيعة وما هو مدعوم على هذا الجهاز.

## 4. أوامر تحقق لاحقة لا تعدّل إعدادات النظام
```bash
# اسم التوزيعة بصورة مستقلة عن platform.platform
grep -E '^(PRETTY_NAME|VERSION_ID|VERSION_CODENAME)=' /etc/os-release

# جرد مقاييس SMBIOS للوحدات المركبة دون عرض أرقام الشرائح التسلسلية
sudo dmidecode -t 17 | grep -E '(^Memory Device|^[[:space:]]*(Size|Locator|Bank Locator|Type|Speed|Configured Memory Speed):)'

# فحص جهاز GPU والتعريف الفعلي
lspci -nnk | grep -A3 -E 'VGA|3D|Display'

# فهرس أجهزة الطاقة، بدون افتراض أن البطارية موجودة
ls -1 /sys/class/power_supply/

# قائمة مستشعرات الحرارة في SIM ستحتاج تطويرًا مستقلًا
```
قد يختلف توفر `dmidecode` أو `lspci` بحسب حزم النظام، وقد تكون بيانات SMBIOS ناقصة أو غير دقيقة. لا ينشر المستخدم أي رقم تسلسلي أو UUID في بلاغ عام.

## 5. نتائج القبول
- **PASS:** نجاح أمر doctor، صيغة JSON قابلة للقراءة، صحة الأعداد الأساسية CPU/RAM، والتعرف على GPU، والتمييز عن المزايا غير المنفذة.
- **OPEN:** عدد وسعة شرائح RAM فيزيائيًا، دعم عدادات Intel GPU، قياس الحرارة الفعلي، معرفة وجود البطارية من sysfs، وإضافة SMART.
- **IMPROVEMENT:** استعمال `/etc/os-release` لتعريف التوزيعة، وإظهار حالات `not_implemented`, `not_present`, `permission_denied` بدل جمعها في `unsupported`.

**التوصية:** FT-002 يحقق قبولًا أوليًا لأمر `doctor` على جهاز حقيقي، لكنه لا يغلق جميع معايير مرحلة P0 قبل البت في النقاط المفتوحة أعلاه.

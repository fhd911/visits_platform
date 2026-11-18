"""بيانات تأسيسية وتجريبية: python manage.py seed_demo [--activity]"""
from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from academic.models import AcademicYear, Holiday, StudyWeek, Term
from accounts.models import Role, User
from assessments.choices import Answer, Phase, ReasonKind, VisitMode, VisitType
from assessments.models import FormItem, FormTemplate
from operations.models import ActivityType, NonExecutionReason, PlanItem, WeeklyPlan
from org.models import Department, School, SchoolAssignment, Sector

TEMPLATES = {
    (VisitType.SUPPORT, ""): ("استمارة زيارة الدعم", [
        ("القيادة المدرسية", "توجد خطة تشغيلية معتمدة ومحدّثة"),
        ("القيادة المدرسية", "تُعقد اجتماعات مجتمعات التعلم المهنية بانتظام"),
        ("التعليم والتعلم", "تتوفر سجلات متابعة أداء الطلاب"),
        ("التعليم والتعلم", "تُطبّق خطط علاجية للطلاب المتعثرين"),
        ("البيئة المدرسية", "تتوفر بيئة صفية آمنة ومحفزة"),
        ("الشراكة", "يُفعَّل التواصل مع أولياء الأمور"),
    ]),
    (VisitType.FIRST_IMPROVEMENT, ""): ("استمارة مدارس الأولى للتحسين", [
        ("التشخيص", "اكتمل التشخيص الأولي لواقع المدرسة"),
        ("التشخيص", "حُددت أولويات التحسين ومؤشراتها"),
        ("التنفيذ", "خطة التحسين معتمدة وموزعة المسؤوليات"),
        ("التنفيذ", "تُنفّذ مبادرات الخطة وفق الجدول الزمني"),
        ("المتابعة", "تتوفر شواهد على أثر المبادرات"),
    ]),
    (VisitType.TECHNICAL, Phase.PLANNING): ("الأداء الفني — التخطيط", [
        ("", "يتوفر توزيع المنهج وخطة زمنية"),
        ("", "تتضمن الخطة أهدافاً قابلة للقياس"),
        ("", "حُددت أساليب التقويم المناسبة"),
    ]),
    (VisitType.TECHNICAL, Phase.REVIEW): ("الأداء الفني — المراجعة", [
        ("", "يسير التنفيذ وفق الخطة الزمنية"),
        ("", "تُوظَّف استراتيجيات تدريس متنوعة"),
        ("", "تتوفر سجلات متابعة الواجبات والتقويم"),
    ]),
    (VisitType.TECHNICAL, Phase.EVALUATION): ("الأداء الفني — التقويم", [
        ("", "تحققت الأهداف المخططة"),
        ("", "حُللت نتائج الطلاب وبُنيت عليها قرارات"),
        ("", "وُثّقت الممارسات المتميزة"),
    ]),
}

SCHOOLS = [
    ("1001", "ابتدائية الفيصلية الأولى", "primary", "boys", 0, False),
    ("1002", "ابتدائية النخيل", "primary", "girls", 2, True),
    ("1003", "متوسطة الملك فهد", "middle", "boys", 1, False),
    ("1004", "متوسطة الروضة", "middle", "girls", 0, False),
    ("1005", "ثانوية الأندلس", "secondary", "boys", 2, True),
    ("1006", "ثانوية الياسمين", "secondary", "girls", 0, False),
    ("1007", "ابتدائية السلام", "primary", "boys", 0, False),
    ("1008", "ابتدائية الريان", "primary", "girls", 1, False),
    ("1009", "متوسطة الصفا", "middle", "boys", 0, True),
    ("1010", "ثانوية المروج", "secondary", "girls", 0, False),
    ("1011", "روضة البراعم", "kg", "girls", 0, False),
    ("1012", "مجمع الشروق التعليمي", "multi", "boys", 1, False),
]


class Command(BaseCommand):
    help = "تهيئة بيانات أساسية وتجريبية لبوابة الزيارات"

    def add_arguments(self, parser):
        parser.add_argument("--activity", action="store_true", help="إنشاء خطط وزيارات تجريبية للأسبوع الماضي")

    @transaction.atomic
    def handle(self, *args, activity=False, **opts):
        year, _ = AcademicYear.objects.get_or_create(
            name="1448هـ", defaults={"start_date": date(2026, 8, 23), "end_date": date(2027, 6, 24), "is_current": True})
        t1, _ = Term.objects.get_or_create(year=year, name="الفصل الدراسي الأول",
                                           defaults={"start_date": date(2026, 8, 23), "end_date": date(2027, 1, 7)})
        t2, _ = Term.objects.get_or_create(year=year, name="الفصل الدراسي الثاني",
                                           defaults={"start_date": date(2027, 1, 17), "end_date": date(2027, 6, 24)})
        t1.generate_weeks(); t2.generate_weeks()
        Holiday.objects.get_or_create(name="إجازة اليوم الوطني", defaults={"start_date": date(2026, 9, 23), "end_date": date(2026, 9, 23)})
        Holiday.objects.get_or_create(name="إجازة نهاية أسبوع مطولة", defaults={"start_date": date(2026, 12, 10), "end_date": date(2026, 12, 10)})

        for (vt, phase), (title, items) in TEMPLATES.items():
            tpl, created = FormTemplate.objects.get_or_create(visit_type=vt, phase=phase, defaults={"title": title})
            if created:
                for i, (section, text) in enumerate(items, 1):
                    FormItem.objects.create(template=tpl, section=section, order=i, text=text)

        for name in ["لقاء تدريبي", "اجتماع إداري", "عمل مكتبي وإعداد تقارير", "ورشة عمل", "مشاركة في لجنة"]:
            ActivityType.objects.get_or_create(name=name)
        for name, cat in [("اعتذار المدرسة لظرف طارئ", "school"), ("تكليف إداري مفاجئ", "admin"),
                          ("إجازة أو ظرف صحي", "supervisor"), ("تعليق الدراسة", "external"),
                          ("تعارض مع اختبارات المدرسة", "school")]:
            NonExecutionReason.objects.get_or_create(name=name, defaults={"category": cat})

        dept, _ = Department.objects.get_or_create(name="قسم الإشراف التربوي")
        sectors = [Sector.objects.get_or_create(name=n, defaults={"code": c})[0]
                   for n, c in [("قطاع الشمال", "N"), ("قطاع الوسط", "C"), ("قطاع الجنوب", "S")]]

        def user(email, name, role, **kw):
            u, created = User.objects.get_or_create(email=email, defaults={"full_name": name, "role": role, **kw})
            if created:
                u.set_unusable_password(); u.save()
            return u

        admin = user("admin@example.com", "مسؤول النظام", Role.ADMIN, is_staff=True, is_superuser=True)
        manager = user("manager@example.com", "أ. سعاد العتيبي", Role.DEPT_MANAGER, department=dept)
        dept.manager = manager; dept.save()
        user("director@example.com", "د. خالد الزهراني", Role.DIRECTOR)
        user("assistant@example.com", "أ. نورة القحطاني", Role.EDU_ASSISTANT)
        sups = [
            user("s1@example.com", "أ. محمد الشهري", Role.SUPERVISOR, department=dept, sector=sectors[0], max_schools=5),
            user("s2@example.com", "أ. هند الغامدي", Role.SUPERVISOR, department=dept, sector=sectors[1], max_schools=4),
            user("s3@example.com", "أ. فهد الدوسري", Role.SUPERVISOR, department=dept, sector=sectors[2], max_schools=4),
            user("s4@example.com", "أ. ريم الحربي", Role.SUPERVISOR, department=dept, sector=sectors[0]),
        ]
        schools = []
        for i, (code, name, stage, gender, prio, fi) in enumerate(SCHOOLS):
            s, _ = School.objects.get_or_create(ministry_code=code, defaults={
                "name": name, "stage": stage, "gender": gender, "priority": prio, "is_first_improvement": fi,
                "sector": sectors[i % 3], "principal_name": "—" if i % 4 == 3 else f"قائد/ة {name.split()[-1]}",
                "students_count": 250 + 37 * i, "teachers_count": 18 + i, "classes_count": 10 + i % 6,
            })
            schools.append(s)
        start = year.start_date
        plan = {0: [0, 1, 2, 3], 1: [4, 5, 6], 2: [7, 8, 9], 3: [10]}
        for si, idxs in plan.items():
            for idx in idxs:
                if not SchoolAssignment.objects.filter(supervisor=sups[si], school=schools[idx]).exists():
                    SchoolAssignment.objects.create(supervisor=sups[si], school=schools[idx], start_date=start)

        if activity:
            self._activity(sups, schools, admin)
        self.stdout.write(self.style.SUCCESS(
            "تمت التهيئة. حسابات الدخول (رمز التحقق يظهر في الطرفية): admin@ manager@ director@ assistant@ s1@..s4@example.com"))

    def _activity(self, sups, schools, admin):
        today = timezone.localdate()
        week = StudyWeek.for_date(today)
        prev = week.previous() if week else None
        if not prev:
            return
        reason = NonExecutionReason.objects.first()
        activity_type = ActivityType.objects.first()
        days = [d["date"] for d in prev.workdays() if not d["holiday"]]
        for sup, idxs in [(sups[0], [0, 1, 2]), (sups[1], [4, 5]), (sups[2], [7, 8])]:
            plan = WeeklyPlan.create_for(sup, prev)
            if plan.items.exists():
                continue
            for n, idx in enumerate(idxs):
                vt = VisitType.FIRST_IMPROVEMENT if schools[idx].is_first_improvement else VisitType.SUPPORT
                item = PlanItem(plan=plan, date=days[n % len(days)], kind="visit", school=schools[idx], visit_type=vt,
                                mode=VisitMode.REMOTE if n == 2 else VisitMode.IN_PERSON)
                item.full_clean(); item.save()
            act = PlanItem(plan=plan, date=days[-1], kind="activity", activity_type=activity_type)
            act.full_clean(); act.save()
            plan.submit()
            items = list(plan.items.order_by("date", "id"))
            for k, item in enumerate(items):
                if k == 1 and sup == sups[1]:
                    item.log_execution(sup, False, reason, "طلبت المدرسة التأجيل")
                    continue
                item.log_execution(sup, True)
                if item.kind == "visit":
                    form = item.visit.form
                    for j, r in enumerate(form.responses.all()):
                        if j % 4 == 1:
                            r.answer, r.reason_kind, r.reason_text = Answer.NO, ReasonKind.NOT_PRESENT, "المسؤول غير متواجد وقت الزيارة"
                        elif j % 5 == 3:
                            r.answer, r.reason_kind, r.reason_text = Answer.NO, ReasonKind.IMPOSSIBLE, "لا تتوفر الإمكانات في المبنى الحالي"
                        else:
                            r.answer = Answer.YES
                        r.save()
                    form.summary = "زيارة اطلاع على سير العمل ومتابعة البنود."
                    form.recommendations = "متابعة البنود المرحّلة في الزيارة القادمة."
                    form.save()
                    if not (sup == sups[2] and k == 1):  # يُترك واحد مفتوحاً لإظهار قاعدة المنع
                        form.close(sup)

"""أدوات مشتركة لبناء بيانات الاختبار."""
from datetime import date, timedelta

from academic.models import AcademicYear, StudyWeek, Term
from accounts.models import Role, User
from assessments.choices import Phase, VisitType
from assessments.models import FormItem, FormTemplate
from operations.models import ActivityType, NonExecutionReason, PlanItem, WeeklyPlan
from org.models import Department, School, SchoolAssignment, Sector


class World:
    """عالم صغير: عام، أسابيع، قسم، مدير، مشرفان، مدارس، قوالب."""

    def __init__(self, today=None, items=3):
        self.today = today or date.today()
        sunday = self.today - timedelta(days=(self.today.weekday() + 1) % 7)
        self.year = AcademicYear.objects.create(name="T", start_date=sunday - timedelta(days=70),
                                                end_date=sunday + timedelta(days=200), is_current=True)
        self.term = Term.objects.create(year=self.year, name="ف1", start_date=self.year.start_date,
                                        end_date=self.year.end_date)
        self.term.generate_weeks()
        self.week = StudyWeek.objects.get(start_date=sunday)
        self.prev_week = self.week.previous()
        self.next_week = self.week.next()
        self.dept = Department.objects.create(name="قسم")
        self.manager = User.objects.create_user("m@x.com", full_name="مدير قسم", role=Role.DEPT_MANAGER, department=self.dept)
        self.dept.manager = self.manager
        self.dept.save()
        self.director = User.objects.create_user("d@x.com", full_name="مدير إدارة", role=Role.DIRECTOR)
        self.assistant = User.objects.create_user("a@x.com", full_name="مساعد", role=Role.EDU_ASSISTANT)
        self.sup = User.objects.create_user("s@x.com", full_name="مشرف", role=Role.SUPERVISOR, department=self.dept)
        self.sup2 = User.objects.create_user("s2@x.com", full_name="مشرف٢", role=Role.SUPERVISOR)
        self.sector = Sector.objects.create(name="قطاع")
        self.school = School.objects.create(ministry_code="1", name="مدرسة أ", sector=self.sector, stage="primary", gender="boys")
        self.fi_school = School.objects.create(ministry_code="2", name="مدرسة ب", sector=self.sector, stage="middle",
                                               gender="girls", is_first_improvement=True)
        self.other_school = School.objects.create(ministry_code="3", name="مدرسة ج", sector=self.sector,
                                                  stage="middle", gender="boys")
        start = self.year.start_date
        SchoolAssignment.objects.create(supervisor=self.sup, school=self.school, start_date=start)
        SchoolAssignment.objects.create(supervisor=self.sup, school=self.fi_school, start_date=start)
        SchoolAssignment.objects.create(supervisor=self.sup2, school=self.other_school, start_date=start)
        self.templates = {}
        for vt, phase in [(VisitType.SUPPORT, ""), (VisitType.FIRST_IMPROVEMENT, ""),
                          (VisitType.TECHNICAL, Phase.PLANNING), (VisitType.TECHNICAL, Phase.REVIEW),
                          (VisitType.TECHNICAL, Phase.EVALUATION)]:
            t = FormTemplate.objects.create(visit_type=vt, phase=phase, title=f"{vt}{phase}")
            for i in range(items):
                FormItem.objects.create(template=t, order=i, text=f"بند {i + 1}")
            self.templates[(vt, phase)] = t
        self.activity = ActivityType.objects.create(name="اجتماع")
        self.reason = NonExecutionReason.objects.create(name="اعتذار المدرسة", category="school")

    def workday(self, week):
        """أول يوم عمل في الأسبوع لا يتجاوز اليوم (للأسبوع الحالي)."""
        return week.start_date

    def plan(self, week=None, sup=None):
        return WeeklyPlan.create_for(sup or self.sup, week or self.prev_week)

    def add_visit(self, plan, school=None, visit_type=VisitType.SUPPORT, phase="", day=None, mode="in_person"):
        item = PlanItem(plan=plan, date=day or plan.week.start_date, kind="visit", school=school or self.school,
                        visit_type=visit_type, phase=phase, mode=mode)
        item.full_clean()
        item.save()
        return item

    def executed_visit(self, plan=None, **kw):
        plan = plan or self.plan()
        item = self.add_visit(plan, **kw)
        item.log_execution(plan.supervisor, True)
        return item.visit.form


def fill(form, answers, summary="ملخص", recommendations="توصيات"):
    """answers: قائمة (answer, reason_kind, reason_text) بترتيب البنود."""
    for r, (ans, kind, text) in zip(form.responses_ordered(), answers):
        r.answer, r.reason_kind, r.reason_text = ans, kind, text
        r.save()
    form.summary, form.recommendations = summary, recommendations
    form.save()

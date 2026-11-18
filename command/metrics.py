"""مؤشرات مركز القيادة. كل مؤشر يعيد None حين لا تكفي البيانات ليُعرض «—» بدل صفر مضلل."""
from collections import Counter
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from academic.models import AcademicYear, StudyWeek
from accounts.models import Role, User
from assessments.choices import OPEN_FORM_STATUSES, FormStatus
from assessments.models import FormInstance, ItemResponse, VisitCycle
from operations.models import ExecutionLog, PlanItem, Visit, WeeklyPlan
from org.models import School, SchoolAssignment

MIN_LOGGED_FOR_RATE = 3
MIN_RESPONSES_FOR_RESULTS = 5


def ratio(num, den, min_den=1):
    if den is None or den < min_den:
        return None
    return round(100 * num / den)


def scope_supervisors(user):
    qs = User.objects.filter(role=Role.SUPERVISOR, is_active=True)
    if user.role == Role.DEPT_MANAGER and not user.is_superuser:
        qs = qs.filter(department__manager=user)
    return qs.select_related("department", "sector")


def period_start():
    """بداية فترة القياس: بداية الفصل الحالي، وإلا بداية العام، وإلا آخر 30 يوماً."""
    today = timezone.localdate()
    week = StudyWeek.for_date(today)
    if week and week.term:
        return week.term.start_date
    year = AcademicYear.current()
    if year:
        return year.start_date
    return today - timedelta(days=30)


def supervisor_indicators(sup, start, today):
    assigned_ids = set(SchoolAssignment.objects.active(today).filter(supervisor=sup).values_list("school_id", flat=True))
    schools = School.objects.filter(pk__in=assigned_ids)
    priority_ids = set(schools.filter(Q(is_first_improvement=True) | Q(priority=School.Priority.HIGH))
                       .values_list("pk", flat=True))
    visits = Visit.objects.filter(supervisor=sup, date__gte=start, date__lte=today)
    visited_ids = set(visits.values_list("school_id", flat=True))
    logged = PlanItem.objects.filter(plan__supervisor=sup, date__gte=start, date__lte=today) \
        .exclude(status=PlanItem.Status.PLANNED)
    logged_n = logged.count()
    executed_n = logged.filter(status=PlanItem.Status.EXECUTED).count()
    weeks = StudyWeek.objects.filter(start_date__gte=start - timedelta(days=6), start_date__lte=today, is_teaching=True)
    weeks_n = weeks.count()
    planned_weeks = WeeklyPlan.objects.filter(supervisor=sup, week__in=weeks, status=WeeklyPlan.Status.SUBMITTED).count()
    open_forms = FormInstance.objects.filter(visit__supervisor=sup, status__in=OPEN_FORM_STATUSES).count()
    closed = FormInstance.objects.filter(visit__supervisor=sup, closed_at__isnull=False, visit__date__gte=start)
    close_days = [(f.closed_at.date() - f.visit.date).days for f in closed.select_related("visit")]
    responses = ItemResponse.objects.filter(form__in=closed)
    resp_n = responses.count()
    resolved_n = responses.filter(Q(answer="yes") | Q(answer="no", reason_kind="impossible")).count()

    ind = {
        "supervisor": sup,
        "assigned": len(assigned_ids),
        "max_schools": sup.max_schools,
        "load": ratio(len(assigned_ids), sup.max_schools) if sup.max_schools else None,
        "visits": visits.count(),
        "coverage": ratio(len(visited_ids & assigned_ids), len(assigned_ids)),
        "execution": ratio(executed_n, logged_n, MIN_LOGGED_FOR_RATE),
        "logged": logged_n,
        "plan_discipline": ratio(planned_weeks, weeks_n),
        "priority_total": len(priority_ids),
        "priority_coverage": ratio(len(visited_ids & priority_ids), len(priority_ids)),
        "open_forms": open_forms,
        "avg_close_days": round(sum(close_days) / len(close_days), 1) if close_days else None,
        "results": ratio(resolved_n, resp_n, MIN_RESPONSES_FOR_RESULTS),
    }
    followup = max(0, 100 - 20 * open_forms) if (closed.exists() or open_forms) else None
    ind["followup"] = followup
    parts = [ind[k] for k in ("coverage", "execution", "plan_discipline", "priority_coverage", "results", "followup")
             if ind[k] is not None]
    has_activity = any(ind[k] is not None for k in ("execution", "results", "followup"))
    ind["composite"] = round(sum(parts) / len(parts)) if len(parts) >= 3 and has_activity else None
    ind["components_n"] = len(parts)
    return ind


def supervisors_table(user):
    start, today = period_start(), timezone.localdate()
    rows = [supervisor_indicators(s, start, today) for s in scope_supervisors(user)]
    # الترتيب بالمؤشر المتوازن لا بعدد الزيارات؛ من لا تكفي بياناته في الأسفل
    rows.sort(key=lambda r: (r["composite"] is None, -(r["composite"] or 0), r["supervisor"].full_name))
    return rows, start


def dashboard(user):
    today = timezone.localdate()
    start = period_start()
    sups = scope_supervisors(user)
    week = StudyWeek.for_date(today)
    schools = School.objects.filter(is_active=True)
    total_schools = schools.count()
    assigned_ids = set(SchoolAssignment.objects.active(today).values_list("school_id", flat=True))
    visited_ids = set(Visit.objects.filter(date__gte=start, date__lte=today).values_list("school_id", flat=True))
    priority = schools.filter(Q(is_first_improvement=True) | Q(priority=School.Priority.HIGH))
    priority_unvisited = priority.exclude(pk__in=visited_ids).select_related("sector")

    week_items = PlanItem.objects.filter(plan__supervisor__in=sups, plan__week=week) if week else PlanItem.objects.none()
    week_logged = week_items.filter(date__lte=today).exclude(status=PlanItem.Status.PLANNED)
    plans_submitted = WeeklyPlan.objects.filter(supervisor__in=sups, week=week,
                                                status=WeeklyPlan.Status.SUBMITTED).count() if week else 0
    next_week = week.next() if week else None
    next_plans = WeeklyPlan.objects.filter(supervisor__in=sups, week=next_week).count() if next_week else 0

    forms = FormInstance.objects.filter(visit__supervisor__in=sups)
    pipeline = {s: forms.filter(status=s).count() for s in FormStatus.values}

    reasons = Counter(
        ExecutionLog.objects.filter(plan_item__plan__supervisor__in=sups, executed=False,
                                    plan_item__date__gte=start).values_list("reason__name", flat=True)
    ).most_common(6)

    visits = Visit.objects.filter(supervisor__in=sups, date__gte=start, date__lte=today)
    by_type = visits.values("visit_type").annotate(n=Count("id"))
    by_mode = visits.values("mode").annotate(n=Count("id"))
    cycles = VisitCycle.objects.filter(school__in=schools)
    sups_n = sups.count()

    return {
        "today": today, "week": week, "period_start": start,
        "total_schools": total_schools,
        "assignment_coverage": ratio(len(assigned_ids & set(schools.values_list("pk", flat=True))), total_schools),
        "unassigned": schools.exclude(pk__in=assigned_ids).count() if total_schools else None,
        "visit_coverage": ratio(len(visited_ids), total_schools),
        "supervisors": sups_n,
        "plans_submitted": plans_submitted,
        "plans_rate": ratio(plans_submitted, sups_n),
        "next_plans": next_plans, "next_week": next_week,
        "week_execution": ratio(week_logged.filter(status=PlanItem.Status.EXECUTED).count(), week_logged.count(),
                                MIN_LOGGED_FOR_RATE),
        "week_planned": week_items.count(),
        "week_unlogged": week_items.filter(date__lte=today, status=PlanItem.Status.PLANNED).count(),
        "pipeline": pipeline,
        "open_forms": pipeline[FormStatus.DRAFT] + pipeline[FormStatus.RETURNED],
        "priority_total": priority.count(),
        "priority_unvisited": priority_unvisited[:8],
        "priority_unvisited_n": priority_unvisited.count(),
        "reasons": reasons,
        "by_type": {r["visit_type"]: r["n"] for r in by_type},
        "by_mode": {r["mode"]: r["n"] for r in by_mode},
        "visits_n": visits.count(),
        "cycles_open": cycles.filter(status=VisitCycle.Status.OPEN).count(),
        "cycles_done": cycles.filter(status=VisitCycle.Status.COMPLETED).count(),
    }

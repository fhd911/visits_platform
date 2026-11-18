import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from academic.models import StudyWeek
from assessments.choices import VisitType
from assessments.models import VisitCycle
from org.models import SchoolAssignment

from .forms import ExecutionForm, PlanItemForm
from .models import PlanBlocked, PlanItem, Visit, WeeklyPlan, allowed_visit_types, open_forms_for


def supervisor_required(view):
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_supervisor:
            raise PermissionDenied
        return view(request, *args, **kwargs)
    wrapper.__name__ = view.__name__
    return wrapper


def _current_week():
    return StudyWeek.for_date(timezone.localdate())


@supervisor_required
def today(request):
    user, d = request.user, timezone.localdate()
    items = PlanItem.objects.filter(plan__supervisor=user, date=d).select_related("school", "activity_type", "visit__form")
    week = _current_week()
    plan = WeeklyPlan.objects.filter(supervisor=user, week=week).first() if week else None
    next_week = week.next() if week else None
    ctx = {
        "today": d,
        "items": items,
        "week": week,
        "plan": plan,
        "plan_stats": plan.stats() if plan else None,
        "open_forms": open_forms_for(user),
        "unlogged": PlanItem.objects.filter(plan__supervisor=user, date__lte=d, status=PlanItem.Status.PLANNED).count(),
        "next_week": next_week,
        "next_plan": WeeklyPlan.objects.filter(supervisor=user, week=next_week).first() if next_week else None,
        "schools_count": SchoolAssignment.objects.active().filter(supervisor=user).count(),
    }
    return render(request, "operations/today.html", ctx)


@supervisor_required
def my_plan(request):
    week = _current_week()
    if week is None:
        messages.warning(request, "لا يوجد أسبوع دراسي مطابق لتاريخ اليوم في التقويم.")
        return redirect("operations:history")
    return redirect("operations:plan", week_id=week.pk)


@supervisor_required
def plan_view(request, week_id):
    user = request.user
    week = get_object_or_404(StudyWeek, pk=week_id)
    plan = WeeklyPlan.objects.filter(supervisor=user, week=week).first()
    blockers = [] if plan else WeeklyPlan.blockers(user, week)
    form = None
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create":
            try:
                WeeklyPlan.create_for(user, week)
                messages.success(request, "أُنشئت خطة الأسبوع.")
            except PlanBlocked as e:
                messages.error(request, e.messages[0])
            except ValidationError as e:
                messages.error(request, " ".join(e.messages))
            return redirect("operations:plan", week_id=week.pk)
        if plan is None:
            raise PermissionDenied
        if action == "add":
            if not plan.is_editable:
                messages.error(request, "الخطة معتمدة ولا يمكن تعديلها.")
                return redirect("operations:plan", week_id=week.pk)
            form = PlanItemForm(request.POST, plan=plan)
            if form.is_valid():
                form.save()
                messages.success(request, "أُضيف البند إلى الخطة.")
                return redirect("operations:plan", week_id=week.pk)
        elif action == "delete":
            item = get_object_or_404(PlanItem, pk=request.POST.get("item"), plan=plan)
            if plan.is_editable and item.status == PlanItem.Status.PLANNED:
                item.delete()
                messages.success(request, "حُذف البند.")
            return redirect("operations:plan", week_id=week.pk)
        elif action == "submit":
            try:
                plan.submit()
                messages.success(request, "اعتُمدت الخطة.")
            except ValidationError as e:
                messages.error(request, " ".join(e.messages))
            return redirect("operations:plan", week_id=week.pk)
        elif action == "reopen" and plan.status == WeeklyPlan.Status.SUBMITTED:
            plan.status = WeeklyPlan.Status.DRAFT
            plan.save(update_fields=["status"])
            return redirect("operations:plan", week_id=week.pk)
    if plan and form is None and plan.is_editable:
        form = PlanItemForm(plan=plan)
    days = []
    if plan:
        items = list(plan.items.select_related("school", "activity_type"))
        for d in week.workdays():
            days.append({**d, "items": [i for i in items if i.date == d["date"]]})
    school_types = {}
    if plan:
        for s in form.fields["school"].queryset if form else []:
            school_types[s.pk] = allowed_visit_types(user, s, week.start_date)
    return render(request, "operations/plan.html", {
        "week": week, "plan": plan, "blockers": blockers, "form": form, "days": days,
        "stats": plan.stats() if plan else None,
        "prev_week": week.previous(), "next_week": week.next(),
        "school_types_json": json.dumps(school_types),
    })


@supervisor_required
def my_schools(request):
    user = request.user
    assignments = SchoolAssignment.objects.active().filter(supervisor=user).select_related("school__sector")
    rows = []
    for a in assignments:
        s = a.school
        last = Visit.objects.filter(school=s).order_by("-date").first()
        my_last = Visit.objects.filter(school=s, supervisor=user).order_by("-date").first()
        cycles = VisitCycle.objects.filter(school=s, status=VisitCycle.Status.OPEN)
        rows.append({"school": s, "last": last, "my_last": my_last,
                     "open_cycles": [(c, c.progress(), len(c.pending_items())) for c in cycles],
                     "types": [VisitType(t).label for t in allowed_visit_types(user, s)]})
    return render(request, "operations/my_schools.html", {"rows": rows})


@supervisor_required
def history(request):
    plans = WeeklyPlan.objects.filter(supervisor=request.user).select_related("week").prefetch_related("items")
    return render(request, "operations/history.html", {"plans": [(p, p.stats()) for p in plans]})


@supervisor_required
def execution(request):
    user = request.user
    d = timezone.localdate()
    if request.method == "POST":
        item = get_object_or_404(PlanItem, pk=request.POST.get("item"), plan__supervisor=user)
        form = ExecutionForm(request.POST, prefix=f"i{item.pk}")
        if form.is_valid():
            try:
                item.log_execution(user, form.cleaned_data["executed"], form.cleaned_data["reason"],
                                   form.cleaned_data["note"])
                if form.cleaned_data["executed"] and item.kind == PlanItem.Kind.VISIT:
                    messages.success(request, "سُجّل التنفيذ. أكمل استمارة الزيارة وأقفلها.")
                    return redirect("assessments:form", pk=item.visit.form.pk)
                messages.success(request, "سُجّل التنفيذ.")
            except ValidationError as e:
                messages.error(request, " ".join(e.messages))
        else:
            messages.error(request, "تحقق من البيانات: " + " ".join(
                str(m) for errs in form.errors.values() for m in errs))
        return redirect(request.POST.get("next") or "operations:execution")
    pending = PlanItem.objects.filter(plan__supervisor=user, date__lte=d, status=PlanItem.Status.PLANNED) \
        .select_related("school", "activity_type").order_by("date")
    recent = PlanItem.objects.filter(plan__supervisor=user, date__lte=d).exclude(status=PlanItem.Status.PLANNED) \
        .select_related("school", "activity_type", "execution__reason", "visit__form").order_by("-date", "-id")[:15]
    return render(request, "operations/execution.html", {
        "pending": [(i, ExecutionForm(prefix=f"i{i.pk}")) for i in pending],
        "recent": recent,
        "reasons_form": ExecutionForm(),
    })

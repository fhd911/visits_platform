from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from assessments.models import VisitCycle
from operations.models import PlanItem, Visit, allowed_visit_types

from .models import School, SchoolAssignment, Sector


def can_view_school(user, school):
    return user.is_leadership or SchoolAssignment.objects.active().filter(supervisor=user, school=school).exists()


@login_required
def school_list(request):
    if not request.user.is_leadership:
        raise PermissionDenied
    qs = School.objects.filter(is_active=True).select_related("sector")
    q = request.GET.get("q", "").strip()
    sector = request.GET.get("sector")
    flag = request.GET.get("flag")
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(ministry_code__icontains=q) | Q(principal_name__icontains=q))
    if sector:
        qs = qs.filter(sector_id=sector)
    if flag == "fi":
        qs = qs.filter(is_first_improvement=True)
    elif flag == "unassigned":
        qs = qs.exclude(pk__in=SchoolAssignment.objects.active().values("school_id"))
    rows = []
    for s in qs:
        sups = list(s.active_supervisors())
        last = Visit.objects.filter(school=s).order_by("-date").first()
        rows.append({"school": s, "supervisors": sups, "last": last})
    return render(request, "org/school_list.html", {
        "rows": rows, "sectors": Sector.objects.all(), "q": q, "sector": sector, "flag": flag,
    })


@login_required
def school_card(request, pk):
    school = get_object_or_404(School.objects.select_related("sector"), pk=pk)
    if not can_view_school(request.user, school):
        raise PermissionDenied
    visits = Visit.objects.filter(school=school).select_related("supervisor", "form")[:20]
    if not request.user.is_leadership:
        # المشرف يرى زيارات «الأولى للتحسين» فقط إن كانت متاحة له في هذه المدرسة
        allowed = allowed_visit_types(request.user, school)
        visits = [v for v in visits if v.visit_type in allowed]
    cycles = [(c, c.progress(), c.pending_items()) for c in
              VisitCycle.objects.filter(school=school).select_related("year", "template")]
    upcoming = PlanItem.objects.filter(school=school, status=PlanItem.Status.PLANNED) \
        .select_related("plan__supervisor").order_by("date")[:5]
    return render(request, "org/school_card.html", {
        "school": school,
        "assignments": SchoolAssignment.objects.filter(school=school).select_related("supervisor").order_by("-start_date"),
        "visits": visits, "cycles": cycles, "upcoming": upcoming,
    })

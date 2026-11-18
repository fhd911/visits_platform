from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render

from assessments.choices import FormStatus, VisitMode, VisitType
from assessments.services import review_queue

from . import metrics


def leadership_required(view):
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_leadership:
            raise PermissionDenied
        return view(request, *args, **kwargs)
    wrapper.__name__ = view.__name__
    return wrapper


@leadership_required
def dashboard(request):
    data = metrics.dashboard(request.user)
    rows, _ = metrics.supervisors_table(request.user)
    pipeline = [(FormStatus(s).label, data["pipeline"][s], s) for s in FormStatus.values]
    return render(request, "command/dashboard.html", {
        **data,
        "pipeline_rows": pipeline,
        "type_rows": [(t.label, data["by_type"].get(t.value)) for t in VisitType],
        "mode_rows": [(m.label, data["by_mode"].get(m.value)) for m in VisitMode],
        "top_rows": rows[:6],
        "queue": review_queue(request.user)[:6],
    })


@leadership_required
def supervisors(request):
    rows, start = metrics.supervisors_table(request.user)
    return render(request, "command/supervisors.html", {"rows": rows, "period_start": start})

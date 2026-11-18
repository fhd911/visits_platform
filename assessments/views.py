from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from .choices import Answer, FormStatus, ReasonKind
from .models import FormInstance
from .services import can_view_form, review_queue


def _save_answers(request, form):
    for r in form.responses.all():
        r.answer = request.POST.get(f"ans_{r.id}", "")
        if r.answer not in Answer.values:
            r.answer = ""
        r.reason_kind = request.POST.get(f"kind_{r.id}", "") if r.answer == Answer.NO else ""
        if r.reason_kind not in ReasonKind.values:
            r.reason_kind = ""
        r.reason_text = request.POST.get(f"reason_{r.id}", "").strip() if r.answer in (Answer.NO, Answer.DEFERRED) else ""
        r.save()
    form.summary = request.POST.get("summary", "").strip()
    form.recommendations = request.POST.get("recommendations", "").strip()
    form.save(update_fields=["summary", "recommendations"])


@login_required
def form_detail(request, pk):
    form = get_object_or_404(FormInstance.objects.select_related("visit__school", "visit__supervisor", "cycle"), pk=pk)
    if not can_view_form(request.user, form):
        raise PermissionDenied
    editable = form.is_open and form.visit.supervisor_id == request.user.id
    errors = []
    if request.method == "POST":
        action = request.POST.get("action")
        if action in ("save", "close"):
            if not editable:
                raise PermissionDenied
            _save_answers(request, form)
            if action == "close":
                try:
                    form.close(request.user)
                    messages.success(request, "أُقفلت الاستمارة وانتقلت إلى مدير القسم.")
                    return redirect("assessments:form", pk=form.pk)
                except ValidationError as e:
                    errors = e.messages
                    messages.error(request, "لا يمكن الإقفال: توجد حقول غير مكتملة.")
            else:
                messages.success(request, "حُفظت المسودة.")
                return redirect("assessments:form", pk=form.pk)
        elif action in ("review", "return"):
            try:
                form.review(request.user, request.POST.get("note"), return_to_supervisor=action == "return")
                messages.success(request, "سُجّلت ملاحظاتك." if action == "review" else "أُعيدت الاستمارة للمشرف.")
                return redirect("assessments:queue")
            except ValidationError as e:
                messages.error(request, " ".join(e.messages))
    ctx = {
        "form": form,
        "responses": form.responses_ordered(),
        "editable": editable,
        "errors": errors,
        "can_review": form.can_review(request.user),
        "can_return": form.can_review(request.user) and form.status == FormStatus.CLOSED,
        "progress": form.cycle.progress(),
        "reviews": form.reviews.select_related("reviewer"),
        "Answer": Answer,
        "ReasonKind": ReasonKind,
        "reason_kinds": ReasonKind.choices,
    }
    return render(request, "assessments/form_detail.html", ctx)


@login_required
def queue(request):
    if not request.user.is_leadership:
        raise PermissionDenied
    return render(request, "assessments/queue.html", {"forms": review_queue(request.user)})

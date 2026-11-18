
from accounts.models import Role

from .models import REVIEW_FLOW, FormInstance


def review_queue(user):
    """الاستمارات التي تنتظر إجراء هذا المستخدم."""
    qs = FormInstance.objects.select_related("visit__school", "visit__supervisor", "cycle")
    if user.is_superuser or user.role == Role.ADMIN:
        return qs.filter(status__in=list(REVIEW_FLOW))
    statuses = [s for s, (role, _) in REVIEW_FLOW.items() if role == user.role]
    if not statuses:
        return qs.none()
    qs = qs.filter(status__in=statuses)
    if user.role == Role.DEPT_MANAGER:
        qs = qs.filter(visit__supervisor__department__manager=user)
    return qs.order_by("closed_at")


def can_view_form(user, form):
    return user.is_leadership or form.visit.supervisor_id == user.id

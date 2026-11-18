from django import template

register = template.Library()

DASH = "—"

STATUS_TONES = {
    # استمارات
    "draft": "warn", "returned": "danger", "closed": "info", "dept_reviewed": "info",
    "director_reviewed": "info", "approved": "ok",
    # بنود الخطة
    "planned": "muted", "executed": "ok", "not_executed": "danger",
    # الخطط
    "submitted": "ok",
    # المسارات
    "open": "info", "completed": "ok",
}


@register.filter
def dash(value):
    """يعرض «—» بدل القيم الفارغة."""
    if value is None or value == "":
        return DASH
    return value


@register.filter
def pct(value):
    if value is None:
        return DASH
    return f"{value}٪"


@register.filter
def tone(status):
    return STATUS_TONES.get(str(status), "muted")


@register.filter
def level(value):
    """تصنيف دلالي لنسبة مئوية."""
    if value is None:
        return "muted"
    if value >= 80:
        return "ok"
    if value >= 50:
        return "warn"
    return "danger"


@register.filter
def get(d, key):
    try:
        return d.get(key)
    except AttributeError:
        return None

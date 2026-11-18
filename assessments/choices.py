from django.db import models


class VisitType(models.TextChoices):
    SUPPORT = "support", "زيارة دعم"
    TECHNICAL = "technical", "زيارة أداء فني"
    FIRST_IMPROVEMENT = "first_improvement", "زيارة الأولى للتحسين"


class Phase(models.TextChoices):
    PLANNING = "planning", "التخطيط"
    REVIEW = "review", "المراجعة"
    EVALUATION = "evaluation", "التقويم"


PHASE_ORDER = [Phase.PLANNING, Phase.REVIEW, Phase.EVALUATION]


class VisitMode(models.TextChoices):
    IN_PERSON = "in_person", "حضورية"
    REMOTE = "remote", "عن بعد"


class Answer(models.TextChoices):
    YES = "yes", "نعم"
    NO = "no", "لا"
    DEFERRED = "deferred", "لم يُستكمل (مؤجَّل)"


class ReasonKind(models.TextChoices):
    NOT_PRESENT = "not_present", "عدم التواجد وقت الزيارة (غير قاطع — يُرحَّل)"
    IMPOSSIBLE = "impossible", "استحالة التوفير (قاطع — لا يُرحَّل)"


class FormStatus(models.TextChoices):
    DRAFT = "draft", "مسودة"
    RETURNED = "returned", "معادة للمشرف"
    CLOSED = "closed", "مقفلة — لدى مدير القسم"
    DEPT_REVIEWED = "dept_reviewed", "لدى مدير الإدارة"
    DIRECTOR_REVIEWED = "director_reviewed", "لدى مساعد الشؤون التعليمية"
    APPROVED = "approved", "معتمدة"


OPEN_FORM_STATUSES = (FormStatus.DRAFT, FormStatus.RETURNED)

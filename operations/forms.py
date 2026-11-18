from django import forms

from org.models import School, SchoolAssignment

from .models import ActivityType, NonExecutionReason, PlanItem


class PlanItemForm(forms.ModelForm):
    date = forms.TypedChoiceField(label="اليوم", coerce=lambda v: __import__("datetime").date.fromisoformat(v))

    class Meta:
        model = PlanItem
        fields = ["date", "kind", "school", "visit_type", "mode", "phase", "activity_type", "notes"]
        widgets = {"kind": forms.RadioSelect}

    def __init__(self, *args, plan, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.plan = plan
        days = [d for d in plan.week.workdays() if not d["holiday"]]
        self.fields["date"].choices = [(d["date"].isoformat(), f'{d["name"]} {d["date"]:%m/%d}') for d in days]
        assigned = SchoolAssignment.objects.active(plan.week.start_date).filter(supervisor=plan.supervisor)
        self.fields["school"].queryset = School.objects.filter(assignments__in=assigned).distinct()
        self.fields["activity_type"].queryset = ActivityType.objects.filter(is_active=True)
        self.fields["visit_type"].required = False
        self.fields["phase"].required = False
        self.fields["school"].empty_label = "— اختر المدرسة —"
        self.fields["activity_type"].empty_label = "— اختر النشاط —"


class ExecutionForm(forms.Form):
    executed = forms.TypedChoiceField(label="التنفيذ", choices=[("1", "نُفّذ"), ("0", "لم يُنفّذ")],
                                      coerce=lambda v: v == "1", widget=forms.RadioSelect)
    reason = forms.ModelChoiceField(label="سبب عدم التنفيذ", required=False,
                                    queryset=NonExecutionReason.objects.filter(is_active=True),
                                    empty_label="— اختر السبب —")
    note = forms.CharField(label="ملاحظة", required=False, max_length=255)

    def clean(self):
        data = super().clean()
        if data.get("executed") is False and not data.get("reason"):
            self.add_error("reason", "اختر سبب عدم التنفيذ.")
        return data

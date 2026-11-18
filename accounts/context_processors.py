def nav(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}
    pending_reviews = 0
    if user.is_leadership:
        from assessments.services import review_queue
        pending_reviews = review_queue(user).count()
    return {"nav_is_supervisor": user.is_supervisor, "nav_is_leadership": user.is_leadership,
            "nav_pending_reviews": pending_reviews}

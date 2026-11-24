"""All /api/v1/ endpoints in one place (guide section 10.1)."""
from django.urls import path, re_path

from apps.accounts import views as acc
from apps.audit import views as aud
from apps.catalog import views as cat
from apps.circulation import views as circ
from apps.core import views as core
from apps.imports import views as imp
from apps.notifications import views as notif

urlpatterns = [
    # auth
    path("auth/csrf", acc.csrf),
    path("auth/login", acc.login_view),
    path("auth/logout", acc.logout_view),
    path("auth/me", acc.me),
    path("auth/password-reset", acc.password_reset),
    path("auth/password-reset/confirm", acc.password_reset_confirm),
    # catalog
    path("books", cat.books),
    path("books/<int:pk>", cat.book_detail),
    path("books/<int:pk>/copies", cat.book_copies),
    path("copies", cat.copies),
    path("copies/<int:pk>", cat.copy_detail),
    path("copies/<int:pk>/status", cat.copy_status),
    path("categories", cat.categories),
    path("authors", cat.authors),
    path("collections", cat.collections),
    # patrons
    path("departments", acc.departments),
    path("patrons", acc.patrons),
    path("patrons/lookup", circ.patron_lookup),
    path("patrons/<int:pk>", acc.patron_detail),
    path("patrons/<int:pk>/status", acc.patron_status),
    path("patrons/<int:pk>/loans", circ.patron_loans),
    path("patrons/<int:pk>/clearance", circ.patron_clearance),
    # circulation
    path("loans", circ.loans),
    path("loans/return", circ.loan_return),
    path("loans/mine", circ.loans_mine),
    path("loans/<int:pk>", circ.loan_detail),
    path("loans/<int:pk>/renew", circ.loan_renew),
    path("loans/<int:pk>/lost", circ.loan_lost),
    path("fines", circ.fines),
    path("fines/mine", circ.fines_mine),
    path("fines/<int:pk>/transactions", circ.fine_transactions),
    # admin
    path("admin/rules", circ.admin_rules),
    path("admin/sections", cat.admin_sections),
    path("admin/closed-days", circ.admin_closed_days),
    path("admin/closed-days/<str:day>", circ.admin_closed_day_delete),
    path("admin/audit", aud.audit_list),
    path("admin/jobs", notif.jobs),
    path("admin/jobs/run-now", notif.jobs_run_now),
    path("admin/jobs/<int:pk>/retry", notif.job_retry),
    path("admin/notifications", notif.notifications),
    path("admin/imports", imp.imports),
    path("admin/imports/<int:pk>", imp.import_detail),
    path("admin/demo/clock", core.demo_clock),
    path("admin/demo/smtp", core.demo_smtp),
    re_path(r"^.*$", core.api_not_found),
]

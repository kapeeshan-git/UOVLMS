from apps.accounts.services import academic_year_of

from ..models import CirculationRule


def find_rule(patron, section_code, today):
    """Rule for (category, computed academic year, section); students fall back to a year-less rule."""
    if not patron.patron_category:
        return None
    qs = CirculationRule.objects.filter(patron_category=patron.patron_category, section_id=section_code)
    year = academic_year_of(patron, today)
    rule = qs.filter(academic_year=year).first() if year is not None else None
    return rule or qs.filter(academic_year__isnull=True).first()

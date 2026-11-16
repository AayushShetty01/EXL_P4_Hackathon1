"""Tests for the translation pitfall library."""

from app.pitfall_library import PITFALLS, list_pitfalls, pitfalls_as_text

REQUIRED = {
    "SAS_MISSING_COMPARE", "SAS_DIVIDE_BY_ZERO", "SAS_MISSING_ARITHMETIC", "LOGISTIC_EVENT_LEVEL", "LOGISTIC_CONVERGENCE",
    "REGULARISATION_DEFAULT", "ROUND_HALF_AWAY", "PERCENTILE_DEFINITION", "SAS_IF_ELSE_ORDER", "SAS_RETAIN_BY_GROUP",
    "SAS_CHAR_COMPARE", "SAS_DATE_EPOCH", "SAS_INT_TRUNC", "R_FACTOR_REFERENCE", "R_PREDICT_TYPE", "R_NA_HANDLING",
    "R_CUT_INTERVALS", "R_INDEXING", "R_GLM_CONVERGENCE",
}


def test_library_has_every_required_pitfall_once():
    """All required ids are present and ids are unique."""
    ids = [p.id for p in PITFALLS]
    assert REQUIRED <= set(ids) and len(ids) == len(set(ids))


def test_filter_and_text_by_language():
    """Filtering by language returns only that language and the text lists each id."""
    r_only = list_pitfalls("R")
    assert r_only and all(p.language == "R" for p in r_only)
    text = pitfalls_as_text("SAS")
    assert "SAS_MISSING_COMPARE" in text and "R_CUT_INTERVALS" not in text


def test_both_languages_get_a_converging_fit():
    """SAS and R translations are both told to fit with Newton or IRLS, never the default BFGS."""
    for language, pitfall_id in (("SAS", "LOGISTIC_CONVERGENCE"), ("R", "R_GLM_CONVERGENCE")):
        fix = next(p.python_fix for p in list_pitfalls(language) if p.id == pitfall_id)
        assert "method='newton'" in fix and "sm.GLM" in fix and "BFGS" in fix
        assert pitfall_id in pitfalls_as_text(language)

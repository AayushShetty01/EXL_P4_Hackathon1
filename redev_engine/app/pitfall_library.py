"""Library of known traps when translating SAS or R code to Python, served by GET /pitfalls and used in prompts."""

from app.schemas import Pitfall

PITFALLS: list[Pitfall] = [
    Pitfall(
        id="SAS_MISSING_COMPARE", language="SAS", title="Missing values compare as smallest",
        description="In SAS a numeric missing value is smaller than any number, so 'x < 5' is true when x is missing. In pandas any comparison with NaN is false.",
        python_fix="Before a '<' or '<=' comparison, test for missing explicitly: treat NaN as minus infinity (for example x.fillna(-np.inf) < 5) so missing records take the same branch as in SAS.",
    ),
    Pitfall(
        id="SAS_DIVIDE_BY_ZERO", language="SAS", title="Division by zero gives missing",
        description="In a SAS DATA step, division by zero returns a missing value with a note in the log. It is not infinity and not an error.",
        python_fix="Replace zero denominators with NaN before dividing, for example a / b.replace(0, np.nan), so the result is NaN, never inf.",
    ),
    Pitfall(
        id="SAS_MISSING_ARITHMETIC", language="SAS", title="Operators propagate missing, functions ignore it",
        description="Arithmetic operators return missing if any operand is missing, but SAS functions such as SUM, MEAN, MAX and MIN ignore missing arguments.",
        python_fix="Use plain operators for '+' and '-' (NaN propagates). For SUM, MEAN, MAX, MIN use the pandas row methods with skipna=True, and note that SUM of all missing is missing (use min_count=1).",
    ),
    Pitfall(
        id="LOGISTIC_EVENT_LEVEL", language="SAS", title="PROC LOGISTIC event level",
        description="PROC LOGISTIC models the lower ordered response value (0) unless DESCENDING or EVENT= is given, which flips the sign of every coefficient.",
        python_fix="Check the PROC LOGISTIC options. With DESCENDING or EVENT='1' model P(target = 1), which is the statsmodels default. Without them, model P(target = 0).",
    ),
    Pitfall(
        id="LOGISTIC_CONVERGENCE", language="SAS", title="Different convergence rules",
        description="SAS and Python optimisers stop on different convergence criteria, so refitted coefficients differ in the last digits.",
        python_fix="Fit with Newton or IRLS until convergence: sm.Logit(y, X).fit(method='newton', maxiter=100, disp=0) or sm.GLM(y, X, family=sm.families.Binomial()).fit(). Never the default BFGS, which can stop before converging. Compare coefficients with a tolerance, not for equality.",
    ),
    Pitfall(
        id="REGULARISATION_DEFAULT", language="SAS", title="scikit-learn regularises by default",
        description="scikit-learn LogisticRegression applies L2 regularisation by default. SAS PROC LOGISTIC and R glm do not.",
        python_fix="Use statsmodels (Logit or GLM with Binomial family), or LogisticRegression(penalty=None).",
    ),
    Pitfall(
        id="ROUND_HALF_AWAY", language="SAS", title="ROUND rounds half away from zero",
        description="SAS ROUND(x, unit) rounds exact halves away from zero. Python round() and numpy.round() round halves to the nearest even number.",
        python_fix="Implement SAS rounding: np.sign(x) * np.floor(np.abs(x) / unit + 0.5) * unit.",
    ),
    Pitfall(
        id="PERCENTILE_DEFINITION", language="SAS", title="Percentile definitions differ",
        description="The default SAS percentile definition (PCTLDEF=5) differs from the numpy default (linear interpolation).",
        python_fix="Check the matching numpy method (for example method='averaged_inverted_cdf' for definition 5) on a small example before using it.",
    ),
    Pitfall(
        id="SAS_IF_ELSE_ORDER", language="SAS", title="IF / ELSE IF takes the first true branch",
        description="An IF / ELSE IF chain assigns the value of the first true condition. The final ELSE catches everything else, including missing values that failed every test.",
        python_fix="Translate with np.select using the conditions in the same order and the ELSE value as default, or with an explicit if / elif chain.",
    ),
    Pitfall(
        id="SAS_RETAIN_BY_GROUP", language="SAS", title="RETAIN and FIRST. / LAST. logic",
        description="RETAIN keeps values across rows and FIRST. / LAST. flags depend on BY group sorting.",
        python_fix="Sort by the BY variables and use groupby with cumulative functions or shift within groups.",
    ),
    Pitfall(
        id="SAS_CHAR_COMPARE", language="SAS", title="Trailing blanks are ignored",
        description="SAS pads character values with blanks and ignores trailing blanks when comparing.",
        python_fix="Apply str.rstrip() before comparing strings.",
    ),
    Pitfall(
        id="SAS_DATE_EPOCH", language="SAS", title="SAS dates start in 1960",
        description="SAS dates count days from 1 January 1960 and datetimes count seconds from that date.",
        python_fix="Convert with pd.to_datetime(value, unit='D', origin='1960-01-01').",
    ),
    Pitfall(
        id="SAS_INT_TRUNC", language="SAS", title="INT truncates toward zero",
        description="SAS INT removes the fractional part, so INT(-2.5) is -2. It is not floor.",
        python_fix="Use np.trunc, not np.floor or //.",
    ),
    Pitfall(
        id="R_FACTOR_REFERENCE", language="R", title="Factor reference level",
        description="glm uses treatment contrasts with the first factor level as reference. Levels are sorted alphabetically unless set with factor(levels=...).",
        python_fix="Build dummy columns in the same order as R, drop the R reference level, and name columns like R (variable name followed by the level).",
    ),
    Pitfall(
        id="R_PREDICT_TYPE", language="R", title="predict returns the linear predictor by default",
        description="predict on a glm returns the linear predictor unless type = 'response' is given.",
        python_fix="Apply the inverse link (1 / (1 + exp(-eta)) for logit) only when the R code uses type = 'response'.",
    ),
    Pitfall(
        id="R_NA_HANDLING", language="R", title="NA handling in glm and ifelse",
        description="glm drops rows with NA by default (na.omit) and ifelse returns NA when the condition is NA.",
        python_fix="Drop rows with NaN in model columns before fitting, and propagate NaN through conditional assignments.",
    ),
    Pitfall(
        id="R_CUT_INTERVALS", language="R", title="cut uses right closed intervals",
        description="cut(x, breaks) builds intervals (a, b] that include the right edge by default, and values outside the breaks become NA.",
        python_fix="Use pd.cut(x, bins=breaks, right=True) and keep the R labels such as '(12,24]'. Do not use np.digitize with its defaults.",
    ),
    Pitfall(
        id="R_GLM_CONVERGENCE", language="R", title="glm fits by IRLS until convergence",
        description="glm estimates by iteratively reweighted least squares and stops only when the deviance converges (epsilon 1e-8, up to 25 iterations). statsmodels Logit with the BFGS optimiser can stop after its default 35 iterations without converging, so refitted coefficients differ by far more than rounding.",
        python_fix="Fit with sm.GLM(y, X, family=sm.families.Binomial()).fit(), which uses IRLS like glm, or sm.Logit(y, X).fit(method='newton', maxiter=100, disp=0), and check that the fit converged. Never the default BFGS.",
    ),
    Pitfall(
        id="R_INDEXING", language="R", title="Indexing starts at 1",
        description="R vectors are indexed from 1 and a:b includes both ends.",
        python_fix="Subtract 1 from positions and use range(a - 1, b) for a:b.",
    ),
]


def list_pitfalls(language: str | None = None) -> list[Pitfall]:
    """All pitfalls, or only those for one source language."""
    return [p for p in PITFALLS if language is None or p.language == language]


def pitfalls_as_text(language: str) -> str:
    """Render the pitfalls for one language as a text block for LLM instructions."""
    return "\n".join(f"- {p.id}: {p.description} Fix: {p.python_fix}" for p in list_pitfalls(language))

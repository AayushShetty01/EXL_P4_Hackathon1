/*******************************************************/
/* PROGRAM : 03_SCORE.SAS                              */
/* PURPOSE : CARDS PD SCORECARD - SCORE AND DECISION   */
/* DATE    : 2019, AMENDED 2023                        */
/*******************************************************/

%let path=/home/your_user_id/M001;
libname m001 "&path";

proc transpose data=m001.coef out=work.coef_wide(drop=_name_) prefix=b_;
  id variable;
  var estimate;
run;

%macro score(in=, out=, file=);
data work.scored;
  if _n_ = 1 then set work.coef_wide;
  set &in;
  length decision $7;

  xbeta = b_Intercept
        + b_woe_util * woe_util + b_woe_payr * woe_payr
        + b_woe_worst * woe_worst + b_woe_arrears * woe_arrears
        + b_woe_trend * woe_trend + b_woe_pay0 * woe_pay0
        + b_woe_limit * woe_limit + b_woe_payavg * woe_payavg;
  pd = 1 / (1 + exp(-xbeta));

  pts = round(487.1229 - 28.8539 * b_Intercept, 0.5)
      + round(-28.8539 * b_woe_util * woe_util, 0.5)
      + round(-28.8539 * b_woe_payr * woe_payr, 0.5)
      + round(-28.8539 * b_woe_worst * woe_worst, 0.5)
      + round(-28.8539 * b_woe_arrears * woe_arrears, 0.5)
      + round(-28.8539 * b_woe_trend * woe_trend, 0.5)
      + round(-28.8539 * b_woe_pay0 * woe_pay0, 0.5)
      + round(-28.8539 * b_woe_limit * woe_limit, 0.5)
      + round(-28.8539 * b_woe_payavg * woe_payavg, 0.5);
  score = round(pts);

  if score < 515 then decision = 'DECLINE';
  else decision = 'APPROVE';
run;

data &out;
  retain ID pd score decision;
  set work.scored(keep=ID pd score decision);
  format pd best32.;
run;

proc export data=&out outfile="&path/&file" dbms=csv replace;
run;
%mend score;

%score(in=m001.dev_woe, out=m001.scored_dev, file=scored_dev_legacy.csv);
%score(in=m001.oot_woe, out=m001.scored_oot, file=scored_oot_legacy.csv);

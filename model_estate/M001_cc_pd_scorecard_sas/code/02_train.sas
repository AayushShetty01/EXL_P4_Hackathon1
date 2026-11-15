/*******************************************************/
/* PROGRAM : 02_TRAIN.SAS                              */
/* PURPOSE : CARDS PD SCORECARD - FIT LOGISTIC MODEL   */
/* DATE    : 2019                                      */
/*******************************************************/

%let path=/home/your_user_id/M001;
libname m001 "&path";

ods output ParameterEstimates=work.pe;
proc logistic data=m001.dev_woe descending;
  model default_flag = woe_util woe_payr woe_worst woe_arrears
                       woe_trend woe_pay0 woe_limit woe_payavg;
run;

data m001.coef;
  set work.pe(rename=(Variable=v Estimate=e));
  length variable $32;
  variable = v;
  estimate = e;
  format estimate best32.;
  keep variable estimate;
run;

proc export data=m001.coef outfile="&path/coefficients_legacy.csv" dbms=csv replace;
run;

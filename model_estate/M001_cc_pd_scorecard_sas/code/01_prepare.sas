/*******************************************************/
/* PROGRAM : 01_PREPARE.SAS                            */
/* PURPOSE : CARDS PD SCORECARD - BUILD WOE VARIABLES  */
/* DATE    : 2019, AMENDED 2023                        */
/*******************************************************/

%let path=/home/your_user_id/M001;
libname m001 "&path";

proc import datafile="&path/dev.csv" out=work.dev_raw dbms=csv replace;
  guessingrows=max;
run;

proc import datafile="&path/oot.csv" out=work.oot_raw dbms=csv replace;
  guessingrows=max;
run;

%macro build(in=, out=);
data &out;
  set &in;

  util = BILL_AMT1 / LIMIT_BAL;
  pay_ratio = PAY_AMT1 / BILL_AMT2;
  worst_status = max(PAY_0, PAY_2, PAY_3, PAY_4, PAY_5, PAY_6);
  months_arrears = (PAY_0 > 0) + (PAY_2 > 0) + (PAY_3 > 0)
                 + (PAY_4 > 0) + (PAY_5 > 0) + (PAY_6 > 0);
  bill_trend = (BILL_AMT1 - BILL_AMT6) / LIMIT_BAL;
  pay_avg = mean(of PAY_AMT1-PAY_AMT6);

  if util = . then woe_util = 0.1724;
  else if util < 0.05 then woe_util = 0.1724;
  else if util < 0.3 then woe_util = 0.3987;
  else if util < 0.6 then woe_util = -0.1028;
  else if util < 0.9 then woe_util = -0.2713;
  else woe_util = -0.2429;

  if pay_ratio < 0.04 then woe_payr = -0.3597;
  else if pay_ratio < 0.06 then woe_payr = 0.089;
  else if pay_ratio < 0.15 then woe_payr = -0.1063;
  else if pay_ratio < 0.5 then woe_payr = 0.0253;
  else if pay_ratio < 1 then woe_payr = 0.4066;
  else woe_payr = 0.5445;

  if worst_status < 0 then woe_worst = 0.5646;
  else if worst_status < 1 then woe_worst = 0.8748;
  else if worst_status < 2 then woe_worst = -0.1288;
  else if worst_status < 3 then woe_worst = -1.0267;
  else woe_worst = -1.7785;

  if months_arrears < 1 then woe_arrears = 0.7866;
  else if months_arrears < 2 then woe_arrears = -0.4088;
  else if months_arrears < 4 then woe_arrears = -1.0057;
  else woe_arrears = -1.8581;

  if bill_trend < -0.05 then woe_trend = -0.4206;
  else if bill_trend < 0.01 then woe_trend = -0.0596;
  else if bill_trend < 0.1 then woe_trend = 0.3691;
  else if bill_trend < 0.3 then woe_trend = 0.413;
  else woe_trend = 0.0566;

  if PAY_0 < 0 then woe_pay0 = 0.4334;
  else if PAY_0 < 1 then woe_pay0 = 0.6744;
  else if PAY_0 < 2 then woe_pay0 = -0.6049;
  else woe_pay0 = -2.0963;

  if LIMIT_BAL < 50000 then woe_limit = -0.7218;
  else if LIMIT_BAL < 100000 then woe_limit = -0.1953;
  else if LIMIT_BAL < 200000 then woe_limit = 0.067;
  else if LIMIT_BAL < 350000 then woe_limit = 0.4053;
  else woe_limit = 0.6697;

  if pay_avg < 1000 then woe_payavg = -0.4477;
  else if pay_avg < 2500 then woe_payavg = -0.2446;
  else if pay_avg < 5000 then woe_payavg = 0.2354;
  else if pay_avg < 10000 then woe_payavg = 0.3673;
  else woe_payavg = 0.9351;

  keep ID default_flag util pay_ratio worst_status months_arrears bill_trend pay_avg
       woe_util woe_payr woe_worst woe_arrears woe_trend woe_pay0 woe_limit woe_payavg;
run;
%mend build;

%build(in=work.dev_raw, out=m001.dev_woe);
%build(in=work.oot_raw, out=m001.oot_woe);

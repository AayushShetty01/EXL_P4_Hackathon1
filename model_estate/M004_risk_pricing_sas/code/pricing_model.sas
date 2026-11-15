/*******************************************************/
/* PROGRAM : PRICING_MODEL.SAS                         */
/* PURPOSE : PERSONAL LOAN RISK BASED PRICING          */
/* DATE    : 2017, AMENDED 2022                        */
/*******************************************************/

libname prc "/sasdata/pricing";

data work.margin_dev;
  set prc.loan_book_2016_2019;
  where status in ('CLOSED', 'ACTIVE') and months_on_book >= 12;
  realised_margin = (interest_income - funding_cost - credit_loss - servicing_cost) / avg_balance;
  log_amount = log(loan_amount);
run;

proc reg data=work.margin_dev outest=prc.margin_coef noprint;
  model realised_margin = pd_at_origination log_amount term_months
                          ltv_ratio channel_digital;
run;
quit;

data prc.pricing_out;
  if _n_ = 1 then set prc.margin_coef(rename=(intercept=c0 pd_at_origination=c_pd
                      log_amount=c_amt term_months=c_term ltv_ratio=c_ltv
                      channel_digital=c_dig));
  set prc.applications;
  log_amount = log(loan_amount);

  if pd_at_origination < 0.02 then price_tier = 'A';
  else if pd_at_origination < 0.05 then price_tier = 'B';
  else if pd_at_origination < 0.10 then price_tier = 'C';
  else if pd_at_origination < 0.20 then price_tier = 'D';
  else price_tier = 'X';

  select (price_tier);
    when ('A') tier_add = 0.010;
    when ('B') tier_add = 0.025;
    when ('C') tier_add = 0.045;
    when ('D') tier_add = 0.075;
    otherwise tier_add = .;
  end;

  exp_margin = c0 + c_pd * pd_at_origination + c_amt * log_amount + c_term * term_months
             + c_ltv * ltv_ratio + c_dig * channel_digital;

  base_rate = 0.0425;
  if price_tier = 'X' then do;
    offer_rate = .;
    decision = 'DECLINE';
  end;
  else do;
    offer_rate = round(base_rate + tier_add + max(0, 0.02 - exp_margin), 0.0005);
    if offer_rate > 0.199 then offer_rate = 0.199;
    decision = 'APPROVE';
  end;

  keep application_id pd_at_origination price_tier exp_margin offer_rate decision;
run;

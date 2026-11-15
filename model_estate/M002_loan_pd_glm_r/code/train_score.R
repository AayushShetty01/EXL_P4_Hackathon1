# train_score.R
# Personal loans PD model - fit GLM, score applications, write outputs
# 2018

dev <- read.csv("data/dev.csv", stringsAsFactors = TRUE)
oot <- read.csv("data/oot.csv", stringsAsFactors = TRUE)

prep <- function(d) {
  d$dur_band <- cut(d$duration_months, breaks = c(0, 12, 24, 36, 72))
  d$log_amount <- log(d$credit_amount)
  d$housing <- factor(d$housing, levels = c("A152", "A151", "A153"))
  d
}

dev <- prep(dev)
oot <- prep(oot)

fit <- glm(default_flag ~ checking_account_status + credit_history + savings_account +
             dur_band + log_amount + installment_rate_pct + housing + other_installment_plans,
           family = binomial, data = dev)

score_set <- function(d) {
  p <- predict(fit, newdata = d, type = "response")
  pts <- round(450 + 40 * log((1 - p) / p))
  dec <- ifelse(pts < 470, "DECLINE", "APPROVE")
  data.frame(ID = d$ID, pd = sprintf("%.17g", p), score = pts, decision = dec)
}

dir.create("golden", showWarnings = FALSE)
write.csv(score_set(dev), "golden/scored_dev_legacy.csv", row.names = FALSE, quote = FALSE)
write.csv(score_set(oot), "golden/scored_oot_legacy.csv", row.names = FALSE, quote = FALSE)

cf <- coef(fit)
write.csv(data.frame(variable = names(cf), estimate = sprintf("%.17g", cf)),
          "golden/coefficients_legacy.csv", row.names = FALSE, quote = 1)

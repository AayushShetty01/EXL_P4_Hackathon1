# Runs the legacy M002 R model and writes its golden outputs into M002_loan_pd_glm_r/golden/.
# Run from the repository root: Rscript model_estate/_tools/make_golden_m002.R

args <- commandArgs(trailingOnly = FALSE)
script_path <- normalizePath(sub("^--file=", "", args[grep("^--file=", args)]))
model_dir <- file.path(dirname(dirname(script_path)), "M002_loan_pd_glm_r")

setwd(model_dir)
sink("golden/run_log.txt", split = TRUE)
cat("M002 golden run on", format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"), "\n")
cat(R.version.string, "\n")
source("code/train_score.R", echo = TRUE, max.deparse.length = Inf)
print(summary(fit))
sink()

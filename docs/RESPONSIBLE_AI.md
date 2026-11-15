# Responsible AI note

ModelPassport uses AI agents to prepare model risk evidence for expert review. A human reviews and signs every stage and remains responsible for approving model use. Every claim and every number the agents write is checked by code.

## Data used

* Public or synthetic data only, never personal data. M001 uses the UCI Default of Credit Card Clients dataset and M002 the UCI Statlog German Credit dataset, both under CC BY 4.0. M003 uses synthetic data from a seeded script; M004 has no data.
* The Taiwan (2005) and German (1994) data are not UK portfolios: their age, geography and collection context limit transferability. Public data can still contain sensitive attributes and is handled under its licence.
* Model owners appear as role titles, never as names. Sex and age band are never model or challenger inputs; they are kept only to test outcomes.

## Privacy and security

* Keys live only in a local `.env` file, which is never committed, and the LLM key is never logged, printed or stored.
* Prompts carry only the model's own files and small extracts. Agents read files through a safe reader that allows only the model estate and run outputs, and always blocks the evaluation answer keys.
* The default LLM is a free tier endpoint, which may retain prompts to improve the provider's products. That is acceptable here because only public data and our own sample code are sent. A bank would use a private deployment within its own cloud tenant, by changing the endpoint settings.

## Human oversight and independence

* Agents never approve their own work. Each of the five stages pauses for a human approve or reject decision, recorded with reviewer, role, comment and review time.
* Validation is independent of development in three ways: validation_lab computes every number with no LLM; the validator agent is separate, sees only the results and can run on a different model; and the reviewer who approved redevelopment cannot approve validation (the API refuses it).
* Automatic approvals exist only for seeding demo runs, use named demo reviewers, are marked automatic in the audit trail and are left out of human review figures. Sign off details are recorded but not authenticated in this prototype.

## No invented facts

* Every sentence the documentation agent writes is a claim with file and line evidence that code checks. Failed claims stay visible as unverified; questions the files cannot answer are marked "SME input needed".
* The validation narrative may only use numbers that exist in the computed results. One rewrite is allowed; numbers that still fail are listed in the report.
* Failures are shown, never hidden: unreached parity, a failed service call or an unrecorded LLM reply stops the stage with its error.

## Fairness

Approval is the favourable outcome. The demographic parity ratio divides the lowest group approval rate by the highest; the equal opportunity difference is the largest approval gap among good customers (target zero); the equalized odds difference is the larger of that gap and the gap among bad customers. Reports show group sizes, overall and class conditional approval rates, observed default rates and mean predicted probabilities, and fairlearn results are cross checked with pandas. Groups below fifty observations stay visible but are left out of comparisons; a missing outcome class gives null rates and a LOW finding. These measures flag disparities to investigate; they do not establish causation or prove the absence of discrimination. Other features can act as proxies, and intersectional groups and uncertainty intervals need further analysis.

## Reading the results

* PSI, CSI, AUC, calibration, binomial and fairness limits are configurable illustrative defaults, not regulatory limits. A Hosmer Lemeshow rejection alone is at most AMBER, because the test is sensitive to sample size.
* A GREEN rating is not an approval, and tests that could not run can coexist with GREEN; reviewers must read the findings. Small samples, missing data and population change make point estimates unstable.
* The holdout sample is a random holdout, not a true out of time sample. Monitoring batches are simulated and must never be presented as production experience.
* Parity proves equivalence on the tested records, not on every input. Input hashes support reproducibility but do not prove data authenticity. The SS1/23 matrix is a simplified team mapping, not a regulatory assessment.

## Safe execution and traceability

* Generated and scoring code runs in a separate process with a time limit and import restrictions (redev_engine for rebuilt models, validation_lab for scoring modules), never inside factory_core. Production use would add operating system isolation, network denial and resource limits.
* Every LLM call (step, model, prompt hash, tokens, time, cached or not), service call, artifact write, stage change and gate decision is an event in a hash chained audit trail; changing, inserting or removing an event breaks the chain, and the API reports it. Recorded replies let a run be replayed without calling a provider.

## Models the product calls at run time

* factory_core: the discovery, documentation, document drift and validator agents call one OpenAI compatible endpoint (by default a Gemini Flash model through Google AI Studio), set by `LLM_BASE_URL` and `LLM_MODEL`; the validator can use a different model through `LLM_MODEL_VALIDATOR`. Temperature is 0.
* redev_engine: code analysis, translation, test writing and mismatch diagnosis use the same kind of endpoint.
* validation_lab: no LLM. The validation report names the model that wrote its narrative.

## Before production use

A bank would also need representative, licensed longitudinal portfolio data; legal and conduct risk review; intersectional fairness tests with uncertainty estimates and proxy analysis; validated model specific thresholds; business impact and stress testing; data lineage, access controls, authenticated approvals and immutable audit retention; and ongoing outcome monitoring.

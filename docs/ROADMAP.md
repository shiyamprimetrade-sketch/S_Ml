# Roadmap

| Phase | State | Next acceptance evidence |
|---|---|---|
| 1 Foundation | Implemented, CI verification in progress | Clean installation and verified PR |
| 2 Stanford ML core | Partial | Regression implemented; classification/SVM, clustering/PCA and further algorithms pending |
| 3 TikTok integration | Partial | Authorized connector export ingestion verified; standalone auth and sync pending |
| 4 Dashboard | Partial | Read-only HTTP API verified; browser rendering and action controls pending |
| 5 Prediction | Pending | Horizon matching, label maturity, chronological purging, minimum data, baseline comparison |
| 6 Recommendations | Partial | Fixed evidence rules only; learned recommendations and production briefs pending |
| 7 Experiments | Partial | Registration only; outcome collection/comparison and result interpretation pending |
| 8 Continuous operation | Pending | Durable scheduler, retry/backoff/rate-limit tests, restart and deployment evidence |
| 9 Expert system | Partial | Missingness/data-window diagnostics only; retention diagnoses require real measurements |
| 10 Release | Pending | All mission criteria verified; version string alone does not imply production release |

Next milestone: implement independently authorized provider lifecycle and a
restart-safe observation worker, with simulated transport tests and a real
read-only health/sync verification after separate app credentials are configured.
Do not request credentials until the application and reviewed scopes are ready.
Collect labelled snapshots before attempting TikTok forecasting. Do not assume
instantaneous provider freshness. Future performance validation must ensure each
training outcome was observable before the validation period; split by post,
never by snapshot, and use matched forecast horizons.

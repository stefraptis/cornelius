# Sub-processors

Version {subprocessors_version}, effective {subprocessors_date}. Draft pending legal review.

Companies that process personal data on our behalf to run {app_name}. All processing takes place in the European Union. We will update this list before adding a sub-processor and notify institutional customers as their agreement requires.

| Sub-processor | Service | Data | Location |
| --- | --- | --- | --- |
| Supabase | Managed PostgreSQL database and authentication | Account data, metadata, analysis results, audit log | EU (Frankfurt) |
| Backblaze | Object storage (B2) | Uploaded videos, streaming renditions, reports | EU Central |
| GPU computing provider (to be confirmed before launch: RunPod or Modal) | Runs the analysis models during an analysis | Video frames in memory during processing only | EU region |
| Hosting provider (to be confirmed before launch) | Runs the web application and API | Traffic, technical logs | EU region |
| Email provider (to be confirmed before launch) | Sign-in links and notifications | Email address, message content | EU data residency |
| Sentry (or equivalent, to be confirmed) | Error monitoring | Technical error reports without video content | EU data residency |

Items marked "to be confirmed" are decided before the first institutional pilot and this page is updated then.

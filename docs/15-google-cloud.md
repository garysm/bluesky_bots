# 15 Google Cloud later

Where each local piece would move if the project outgrows this PC. Nothing here has been set up or tested.

| Local piece | Google Cloud equivalent | Note |
| --- | --- | --- |
| `stream` command | Small always-on Compute Engine VM, or a Cloud Run worker pool | It holds an outbound connection and serves no requests, so an ordinary Cloud Run service is a poor fit. |
| `data/raw/*.jsonl` | Cloud Storage bucket with a rule deleting objects after a few days | Keeps the landing area a buffer. |
| The store | A new storage backend over BigQuery or Cloud SQL for PostgreSQL | One class implementing the `Store` interface ([05](05-storage.md)); [17](17-choosing-storage.md) compares the options. `storage copy` moves the data. |
| `storage load`, `topics assign`, `signals`, `narratives` commands | Cloud Run jobs started by Cloud Scheduler | Same Python in a container. |
| `classify` workflow | Cloud Run job | The workflow code does not change. |
| A model on a local runtime | A hosted model (Gemini, hosted `gemma-4-*`, or any LiteLLM provider), or the same runtime on Cloud Run with a GPU | For hosted models only the `.env` string changes ([16](16-choosing-models.md)); ADK 2.7.1 routes `gemini-*` and `gemma-4*` names to its Gemini class. |
| `topics/*.yaml` | The same files, in the container image or a bucket | `TOPICS_DIR` says where. |
| `.env` | Secret Manager | `ANON_SALT` must keep the same value or anonymous IDs change. |
| HTML reports | Static files in a Cloud Storage bucket | |

The main costs would be GPU hours for labeling, the always-on stream, and BigQuery queries if dashboards read raw tables instead of daily summaries.

The same containers would run on AWS (ECS or Fargate, S3, Athena or RDS). Only the hosted Gemma option is specific to Google.

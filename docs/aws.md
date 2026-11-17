# On AWS

Everything here runs on one machine: the lake is a folder and the warehouse a DuckDB file. That keeps the tests fast and
the evaluation reproducible. Nothing in this repository has been deployed to AWS. This is how the same pieces map
onto it, and what would change.

| here | on AWS | what changes |
|---|---|---|
| `lake/raw/<source>/` | an S3 prefix per source, written by the metering operators' SFTP drop, the HEMS vendor's export and the trading system | `ftd/ingest.py` lists with boto3 instead of `glob`; the content hash and the manifest stay as they are |
| `lake/bronze/` and `_manifest.parquet` | an S3 prefix registered in the Glue catalog | the manifest becomes a table, and landing a file a conditional put, so two runs cannot land it twice |
| dbt on DuckDB | dbt-athena on the same bronze, or dbt-duckdb reading S3 through `httpfs` on a small worker | the staging models read `read_parquet('s3://…')` or a Glue source; DuckDB-only functions (`ASOF JOIN`, `timezone()`) need Athena equivalents in `macros/` |
| the Airflow DAG | Amazon MWAA, or Airflow on ECS | `FTD_LAKE` and `FTD_DUCKDB` point at S3 and the warehouse; task code does not change |
| the Dash app | a container on ECS behind an ALB, reading the marts | `dashboard/data.py` already reads either a DuckDB file or Parquet marts |
| `config/*.yaml` | the same files in the repository | secrets (S3 roles, the market data API key) in Secrets Manager, never in config |

Infrastructure as code for this (S3 buckets with lifecycle rules, Glue database, MWAA environment, IAM roles per task)
would be a Terraform module per environment. It is not written here, because it could not be applied or tested from
this repository.

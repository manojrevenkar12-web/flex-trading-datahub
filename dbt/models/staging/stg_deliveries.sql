-- The landing manifest: every raw file, and whether it was landed or skipped as a repeat delivery.
select file, sha256, status from read_parquet('{{ var("lake") }}/bronze/_manifest.parquet')

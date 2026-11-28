-- Reverse of 067_halftime_pdf_leads.sql. Never applied by the migration runner.
-- Destroys every captured lead; export first if they are needed.
DROP TABLE IF EXISTS halftime_pdf_leads;

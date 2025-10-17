GRANT SELECT, UPDATE ON submissions TO sd_submit_ingest;
GRANT SELECT, UPDATE ON files TO sd_submit_ingest;

GRANT SELECT ON submissions TO sd_submit_reader;
GRANT SELECT ON objects TO sd_submit_reader;
GRANT SELECT ON files TO sd_submit_reader;
GRANT SELECT ON registrations TO sd_submit_reader;

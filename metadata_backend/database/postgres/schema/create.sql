
CREATE TABLE api_keys (
	key_id VARCHAR NOT NULL,
	user_id VARCHAR NOT NULL,
	user_key_id VARCHAR NOT NULL,
	api_key VARCHAR NOT NULL,
	salt VARCHAR NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (key_id, user_key_id),
	UNIQUE (user_id, user_key_id)
)



CREATE TABLE submissions (
	submission_id VARCHAR(128) NOT NULL,
	name VARCHAR NOT NULL,
	project_id VARCHAR NOT NULL,
	bucket VARCHAR(64),
	workflow VARCHAR(10) NOT NULL,
	title VARCHAR,
	description TEXT,
	created TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	modified TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	is_published BOOLEAN DEFAULT false NOT NULL,
	is_ingested BOOLEAN DEFAULT false NOT NULL,
	published TIMESTAMP WITH TIME ZONE,
	ingested TIMESTAMP WITH TIME ZONE,
	document JSONB NOT NULL,
	PRIMARY KEY (submission_id),
	CONSTRAINT ck_workflow CHECK (workflow IN ('SD', 'FEGA', 'Bigpicture'))
)


CREATE INDEX ix_submissions_modified ON submissions (modified)
CREATE INDEX ix_submissions_is_ingested ON submissions (is_ingested)
CREATE INDEX ix_submissions_is_published ON submissions (is_published)
CREATE INDEX ix_submissions_created ON submissions (created)

CREATE TABLE objects (
	object_id VARCHAR(128) NOT NULL,
	name VARCHAR,
	object_type VARCHAR NOT NULL,
	submission_id VARCHAR(128) NOT NULL,
	project_id VARCHAR NOT NULL,
	title VARCHAR,
	description TEXT,
	document JSONB,
	xml_document XML,
	created TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	modified TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (object_id),
	FOREIGN KEY(submission_id) REFERENCES submissions (submission_id) ON DELETE CASCADE
)


CREATE INDEX ix_objects_modified ON objects (modified)
CREATE INDEX ix_objects_submission_id ON objects (submission_id)
CREATE INDEX ix_objects_created ON objects (created)

CREATE TABLE files (
	file_id VARCHAR(128) NOT NULL,
	submission_id VARCHAR(128) NOT NULL,
	object_id VARCHAR(128),
	path VARCHAR(1024) NOT NULL,
	bytes INTEGER,
	checksum_method VARCHAR(16),
	unencrypted_checksum VARCHAR(128),
	encrypted_checksum VARCHAR(128),
	ingest_status VARCHAR(9) DEFAULT 'submitted' NOT NULL,
	ingest_error VARCHAR,
	ingest_error_type VARCHAR(15),
	ingest_error_count INTEGER,
	created TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	modified TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (file_id),
	UNIQUE (submission_id, path),
	CONSTRAINT ck_checksum_method CHECK (checksum_method IN ('MD5', 'SHA256')),
	CONSTRAINT ck_ingest_status CHECK (ingest_status IN ('submitted', 'verified', 'ready', 'error')),
	CONSTRAINT ck_ingest_error_type CHECK (ingest_error_type IN ('user_error', 'transient_error', 'permanent_error')),
	FOREIGN KEY(submission_id) REFERENCES submissions (submission_id) ON DELETE CASCADE,
	FOREIGN KEY(object_id) REFERENCES objects (object_id) ON DELETE CASCADE
)


CREATE INDEX ix_files_modified ON files (modified)
CREATE INDEX ix_files_object_id ON files (object_id)
CREATE INDEX ix_files_submission_id ON files (submission_id)
CREATE INDEX ix_files_created ON files (created)
CREATE INDEX ix_files_ingest_status ON files (ingest_status)

CREATE TABLE registrations (
	submission_id VARCHAR(128) NOT NULL,
	object_id VARCHAR(128),
	title TEXT NOT NULL,
	description TEXT NOT NULL,
	object_type VARCHAR(256),
	doi VARCHAR(256) NOT NULL,
	metax_id VARCHAR(256),
	datacite_url VARCHAR(1024),
	rems_url VARCHAR,
	rems_resource_id VARCHAR,
	rems_catalogue_id VARCHAR,
	created TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	modified TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (submission_id),
	FOREIGN KEY(submission_id) REFERENCES submissions (submission_id) ON DELETE CASCADE,
	FOREIGN KEY(object_id) REFERENCES objects (object_id) ON DELETE CASCADE
)


CREATE INDEX ix_registrations_created ON registrations (created)
CREATE INDEX ix_registrations_modified ON registrations (modified)
CREATE UNIQUE INDEX ix_registrations_object_id ON registrations (object_id)
COMMENT ON COLUMN registrations.doi IS 'Digital Object identifier'
COMMENT ON COLUMN registrations.metax_id IS 'Metax identifier'
COMMENT ON COLUMN registrations.datacite_url IS 'Datacite discovery URL'

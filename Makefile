# Write a line to .env and tests/integration/.env files.
define write_line
@printf "%s\n" "$(1)" >> .env
@printf "%s\n" "$(1)" >> tests/integration/.env
endef

# Write the secret to .env file.
define write_secret
printf "%s=" $(1) >> .env; \
vault kv get --field=$(3) secret/$(2) >> .env; \
echo >> .env;
endef

# Write the secret to .env, tests/integration/.env and tests/integration/.env.secret files.
define write_integration_test_secret
secret_value=$$(vault kv get --field=$(3) secret/$(2)); \
printf "%s=%s\n" $(1) "$$secret_value" >> .env; \
printf "%s=%s\n" $(1) "$$secret_value" >> tests/integration/.env; \
printf "%s=%s\n" $(1) "$$secret_value" >> tests/integration/.env.secret;
endef


# Default target
# Print list of available targets. Only rows in the format `target: ## description` are printed
help:
	@echo "Available targets:"
	@awk '/^[a-zA-Z0-9_-]+:.*?## / {printf "  %-20s %s\n", $$1, substr($$0, index($$0, "##") + 3)}' $(MAKEFILE_LIST)

get_env: ## Get secrets needed for integration tests from vault
	@vault -v > /dev/null 2>&1 || { echo "Vault CLI is not installed. Aborting."; exit 1; }
	@if [ -z "$$VAULT_ADDR" ]; then \
		echo "VAULT_ADDR environment variable needs to be set. Aborting."; \
		exit 1; \
	fi

	# Create empty .env.secret and private_jwks.json file.
	@mkdir -p private
	> tests/integration/.env.secret
	> private/private_jwks.json

	# Create .tests/integration/.env file.
	cp tests/integration/.env.example tests/integration/.env
	cp tests/integration/.env.example .env

	$(call write_line,### VAULT SECRETS START ###)

	# Write secrets to .env and tests/integration/.env files.
	@export VAULT_TOKEN=$$(vault login -method=oidc -token-only); \
	$(call write_secret,CSC_LDAP_HOST,sd-submit/secrets,ldap_host) \
	$(call write_secret,CSC_LDAP_USER,sd-submit/secrets,ldap_user) \
	$(call write_secret,CSC_LDAP_PASSWORD,sd-submit/secrets,ldap_password) \
	$(call write_secret,SDS_AAI_CLIENT_ID,sd-submit/secrets,sds_aai_id) \
	$(call write_secret,SDS_AAI_SECRET,sd-submit/secrets,sds_aai_secret) \
	$(call write_secret,SDS_AAI_URL,sd-submit/secrets,sds_aai_url) \
	$(call write_secret,LS_AAI_CLIENT_ID,sd-submit/secrets,ls_aai_id) \
	$(call write_secret,LS_AAI_SECRET,sd-submit/secrets,ls_aai_secret) \
	$(call write_secret,LS_AAI_URL,sd-submit/secrets,ls_aai_url) \
	$(call write_secret,KEYSTONE_ENDPOINT,sd-submit/secrets,pouta_host) \
	$(call write_integration_test_secret,DATACITE_API,sd-submit/datacite_test,DOI_API) \
	$(call write_integration_test_secret,DATACITE_USER,sd-submit/datacite_test,DOI_USER) \
	$(call write_integration_test_secret,DATACITE_KEY,sd-submit/datacite_test,DOI_KEY) \
	$(call write_integration_test_secret,DATACITE_DOI_PREFIX,sd-submit/datacite_test,DOI_PREFIX) \
	$(call write_integration_test_secret,CSC_PID_URL,sd-submit/pid,PID_URL) \
	$(call write_integration_test_secret,CSC_PID_KEY,sd-submit/pid,PID_APIKEY) \
	$(call write_integration_test_secret,METAX_URL,sd-submit/metax_test,METAX_V3_TEST_URL) \
	$(call write_integration_test_secret,METAX_TOKEN,sd-submit/metax_test,METAX_V3_TEST_TOKEN) \
	$(call write_integration_test_secret,ROR_URL,sd-submit/secrets,ror_url) \
	$(call write_integration_test_secret,S3_ENDPOINT,sd-submit/secrets,allas_host) \
	$(call write_integration_test_secret,S3_REGION,sd-submit/secrets,s3_region) \
	$(call write_integration_test_secret,STATIC_S3_ACCESS_KEY_ID,sd-submit/secrets,s3_access_key) \
	$(call write_integration_test_secret,STATIC_S3_SECRET_ACCESS_KEY,sd-submit/secrets,s3_secret_key) \
	$(call write_integration_test_secret,SD_SUBMIT_PROJECT_ID,sd-submit/secrets,sd_submit_project_id) \
	$(call write_integration_test_secret,USER_S3_ACCESS_KEY_ID,sd-submit/secrets,s3_test_user_access_key) \
	$(call write_integration_test_secret,USER_S3_SECRET_ACCESS_KEY,sd-submit/secrets,s3_test_user_secret_key) \
    $(call write_integration_test_secret,REMS_URL,sd-submit/secrets,rems_url) \
    $(call write_integration_test_secret,REMS_USER,sd-submit/secrets,rems_user) \
    $(call write_integration_test_secret,REMS_KEY,sd-submit/secrets,rems_key) \
    $(call write_integration_test_secret,REMS_DISCOVERY_URL,sd-submit/secrets,rems_discovery_url) \
	vault kv get --field=oidc_jwks secret/sd-submit/secrets >> private/private_jwks.json;

	$(call write_line,### VAULT SECRETS END ###)

	@echo "Secrets written successfully"

get_ci_env: ## Get secrets needed for CI tests from vault
	@vault -v > /dev/null 2>&1 || { echo "Vault CLI is not installed. Aborting."; exit 1; }
	@if [ -z "$$VAULT_ADDR" ]; then \
		echo "VAULT_ADDR environment variable needs to be set. Aborting."; \
		exit 1; \
	fi

	# Copy test JWKS file to private directory.
	@mkdir -p private
	cp tests/test_files/jwks.json private/private_jwks.json

	# Create .tests/integration/.env file.
	cp tests/integration/.env.example tests/integration/.env

	$(call write_line,### VAULT SECRETS START ###)

	# Write secrets to .env file.
	@export VAULT_TOKEN=$$(vault write -field=token auth/approle/login role_id="$$VAULT_ROLE_ID" secret_id="$$VAULT_SECRET_ID"); \
	$(call write_integration_test_secret,DATACITE_API,sd-submit/datacite_test,DOI_API) \
	$(call write_integration_test_secret,DATACITE_USER,sd-submit/datacite_test,DOI_USER) \
	$(call write_integration_test_secret,DATACITE_KEY,sd-submit/datacite_test,DOI_KEY) \
	$(call write_integration_test_secret,DATACITE_DOI_PREFIX,sd-submit/datacite_test,DOI_PREFIX) \
	$(call write_integration_test_secret,CSC_PID_URL,sd-submit/pid,PID_URL) \
	$(call write_integration_test_secret,CSC_PID_KEY,sd-submit/pid,PID_APIKEY) \
	$(call write_integration_test_secret,METAX_URL,sd-submit/metax_test,METAX_V3_TEST_URL) \
	$(call write_integration_test_secret,METAX_TOKEN,sd-submit/metax_test,METAX_V3_TEST_TOKEN) \
	$(call write_integration_test_secret,ROR_URL,sd-submit/secrets,ror_url) \
	$(call write_integration_test_secret,S3_ENDPOINT,sd-submit/secrets,allas_host) \
	$(call write_integration_test_secret,S3_REGION,sd-submit/secrets,s3_region) \
	$(call write_integration_test_secret,STATIC_S3_ACCESS_KEY_ID,sd-submit/secrets,s3_access_key) \
	$(call write_integration_test_secret,STATIC_S3_SECRET_ACCESS_KEY,sd-submit/secrets,s3_secret_key) \
	$(call write_integration_test_secret,SD_SUBMIT_PROJECT_ID,sd-submit/secrets,sd_submit_project_id) \
	$(call write_integration_test_secret,USER_S3_ACCESS_KEY_ID,sd-submit/secrets,s3_test_user_access_key) \
	$(call write_integration_test_secret,USER_S3_SECRET_ACCESS_KEY,sd-submit/secrets,s3_test_user_secret_key) \
    $(call write_integration_test_secret,REMS_URL,sd-submit/secrets,rems_url) \
    $(call write_integration_test_secret,REMS_USER,sd-submit/secrets,rems_user) \
    $(call write_integration_test_secret,REMS_KEY,sd-submit/secrets,rems_key) \
    $(call write_integration_test_secret,REMS_DISCOVERY_URL,sd-submit/secrets,rems_discovery_url)

	$(call write_line,### VAULT SECRETS END ###)

	@echo "CI Secrets written successfully"

get_env_demo: ## Create an empty .env file for demo purposes
	# Copy .env.example
	cp tests/integration/.env.example .env

	# Write all env variables markers to .env file
	$(call write_line,DATACITE_API=placeholder)
	$(call write_line,DATACITE_USER=placeholder)
	$(call write_line,DATACITE_KEY=placeholder)
	$(call write_line,DATACITE_DOI_PREFIX=placeholder)
	$(call write_line,CSC_PID_URL=placeholder)
	$(call write_line,CSC_PID_KEY=placeholder)
	$(call write_line,METAX_URL=placeholder)
	$(call write_line,METAX_TOKEN=placeholder)
	$(call write_line,ROR_URL=placeholder)

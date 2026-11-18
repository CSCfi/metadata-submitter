# Write a line to .env and tests/integration/.env files.
define write_line
@printf "%s\n" "$(1)" >> .env
@printf "%s\n" "$(1)" >> tests/integration/.env
endef

# Write the secret to .env file.
define write_secret
printf "%s=" $(1) >> .env; \
vault kv get --field=$(1) secret/$(2) >> .env; \
echo >> .env;
endef

# Write out a set of JSON secrets from a single path to .env file.
define write_secret_group
data=$$(vault kv get -format=json secret/$(1)| jq -r '.data.data | to_entries | .[] | "\(.key)=\(.value)"'); \
printf "%s\n" "$$data" >> .env;
endef

# Write out a set of JSON secrets from a single path to .env, tests/integration/.env and tests/integration/.env.secret files.
define write_integration_test_secret_group
data=$$(vault kv get -format=json secret/$(1)| jq -r '.data.data | to_entries | .[] | "\(.key)=\(.value)"'); \
printf "%s\n" "$$data" >> .env; \
printf "%s\n" "$$data" >> tests/integration/.env; \
printf "%s\n" "$$data" >> tests/integration/.env.secret;
endef

define write_secret_to_file
mkdir -p "$$(dirname "$(1)")" && \
(umask 077; vault kv get --field="$(3)" "secret/$(2)" > "$(1)") || (rm -f "$(1)"; exit 1);
endef

# Default target
# Print list of available targets. Only rows in the format `target: ## description` are printed
help:
	@echo "Available targets:"
	@awk '/^[a-zA-Z0-9_-]+:.*?## / {printf "  %-20s %s\n", $$1, substr($$0, index($$0, "##") + 3)}' $(MAKEFILE_LIST)

db_upgrade: ## Apply Alembic migrations to the configured database
	uv run alembic upgrade head

db_stamp: ## Stamp an existing schema with an Alembic revision, usage: make db_stamp revision=head
	uv run alembic stamp $(if $(revision),$(revision),head)

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

	@printf "%s\n" "OIDC_VERIFY_ID_TOKEN=True" >> .env
	@printf "%s\n" "INGEST_SCAN_INTERVAL=60" >> .env
	$(call write_line,### VAULT SECRETS START ###)

	# Write secrets to .env and tests/integration/.env files.
	@export VAULT_TOKEN=$$(vault login -method=oidc -token-only); \
	$(call write_secret_group,sd-submit/ldap) \
	$(call write_secret_group,sd-submit/oidc) \
	$(call write_secret_group,sd-submit/nbis_jwt) \
	$(call write_secret_group,sd-submit/sda) \
	$(call write_secret,KEYSTONE_ENDPOINT,sd-submit/pouta) \
	$(call write_integration_test_secret_group,sd-submit/datacite_test) \
	$(call write_integration_test_secret_group,sd-submit/pid) \
	$(call write_integration_test_secret_group,sd-submit/metax_test) \
	$(call write_integration_test_secret_group,sd-submit/s3) \
	$(call write_integration_test_secret_group,sd-submit/rems) \
	$(call write_integration_test_secret_group,sd-submit/uv) \
	$(call write_secret_to_file,$$HOME/.config/pnpm/auth.ini,artifactory,npmrc) \
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
	cp tests/test_files/keys/jwks.json private/private_jwks.json

	# Create .tests/integration/.env file.
	cp tests/integration/.env.example tests/integration/.env

	$(call write_line,### VAULT SECRETS START ###)

	# Write secrets to .env file.
	@export VAULT_TOKEN=$$(vault write -field=token auth/approle/login role_id="$$VAULT_ROLE_ID" secret_id="$$VAULT_SECRET_ID"); \
	$(call write_integration_test_secret_group,sd-submit/datacite_test) \
	$(call write_integration_test_secret_group,sd-submit/pid) \
	$(call write_integration_test_secret_group,sd-submit/metax_test) \
	$(call write_integration_test_secret_group,sd-submit/s3) \
	$(call write_integration_test_secret_group,sd-submit/rems) \
	$(call write_integration_test_secret_group,sd-submit/uv)

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

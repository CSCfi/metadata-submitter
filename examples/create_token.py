"""Example user token usage.

A user token can be generated as a convenience tool for programmatic use of metadata-submitter.
AAI tokens expire in 1 hour, the user token can be generated after retrieving your personal signing
key from the API, and be used in place of the AAI token for easier authentication.

1. Get a valid AAI token from an OIDC Relying Party, or the UI
2. Request `GET /v1/users/current/key` to generate a new signing key
3. Generate a token with the instructions in this script
4. Use the token as a Bearer token, with `valid=timestamp` and `userId=user_id` query parameters
"""

import hmac
import time

import requests

# settings
user_id = "myuserid"
signing_key = "mysigningkey"
valid_for = 300
timestamp = str(int(time.time() + valid_for))  # the time 5 minutes from now
message = timestamp + user_id  # the message that will be signed

# the signing process
token = hmac.new(key=signing_key.encode("utf-8"), msg=message.encode("utf-8"), digestmod="sha256").hexdigest()

# your token
print(token)

# use this token as a Bearer token, with `valid=timestamp` and `userId=user_id` query parameters
headers = {"Authorization": f"Bearer {token}"}
response = requests.get(f"http://localhost:5430/v1/users/current?valid={timestamp}&userId={user_id}", headers=headers)
print(response.json())

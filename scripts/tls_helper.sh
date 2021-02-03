#!/bin/bash

mkdir -p config && \
openssl req -x509 -nodes -days 365 \
                  -newkey rsa:2048 -sha256 \
                  -subj '/O=root' \
                  -keyout config/cakey \
                  -out config/cacert


openssl req -nodes -new -days 365 -newkey rsa:2048 \
	    -sha256 -subj '/CN=localhost' \
	    -keyout config/key \
	    -out config/cert.csr

openssl x509 -req -CAcreateserial -sha256 \
              -CA config/cacert \
              -CAkey config/cakey \
              -in config/cert.csr \
              -out config/cert

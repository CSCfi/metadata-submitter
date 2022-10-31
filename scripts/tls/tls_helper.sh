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

openssl req -nodes -new -days 365 -newkey rsa:2048 \
	    -sha256 -subj '/CN=database' \
	    -keyout config/key2 \
	    -out config/cert2.csr

openssl x509 -req -CAcreateserial -sha256 \
              -CA config/cacert \
              -CAkey config/cakey \
              -in config/cert2.csr \
              -out config/cert2 \
              -extfile scripts/tls/extfile.ext

openssl req -nodes -new -days 365 -newkey rsa:2048 \
	    -sha256 -subj '/CN=messagebroker' \
	    -keyout config/key3 \
	    -out config/cert3.csr

openssl x509 -req -CAcreateserial -sha256 \
              -CA config/cacert \
              -CAkey config/cakey \
              -in config/cert3.csr \
              -out config/cert3 \
              -extfile scripts/tls/extfile.ext

cat config/key config/cert > config/combined
cat config/key2 config/cert2 > config/combined2
mkdir -p config/mq
cp config/cacert config/mq/
cp config/key3 config/mq/
cp config/cert3 config/mq/

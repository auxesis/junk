encrypt:
	tar czvf secrets.tar.gz client_secret.json credentials.yaml wfh-calendar.yaml
	travis encrypt-file --force secrets.tar.gz
	git commit -m "Update secrets" secrets.tar.gz.enc

all: decrypt deploy

decrypt:
	openssl aes-256-cbc -K $encrypted_c6aa3620beeb_key -iv $encrypted_c6aa3620beeb_iv -in secrets.tar.gz.enc -out secrets.tar.gz -d
	tar zxvf secrets.tar.gz

deploy:
	cf push hello

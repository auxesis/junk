all: decrypt deploy

export PATH := bin:$(PATH)

encrypt:
	tar czvf secrets.tar.gz client_secret.json credentials.yaml wfh-calendar.yaml
	travis encrypt-file --force secrets.tar.gz
	git commit -m "Update secrets" secrets.tar.gz.enc

decrypt:
	@openssl aes-256-cbc -K $(encrypted_c6aa3620beeb_key) -iv $(encrypted_c6aa3620beeb_iv) -in secrets.tar.gz.enc -out secrets.tar.gz -d
	tar zxvf secrets.tar.gz

cf:
	wget 'https://cli.run.pivotal.io/stable?release=linux64-binary&source=github' -O cf.tar.gz
	mkdir -p bin
	tar zxvf cf.tar.gz -C bin

deploy: cf
	@cf login -a https://api.run.pivotal.io -u $(CF_USERNAME) -p $(CF_PASSWORD) -o $(CF_ORG) -s $(CF_SPACE)
	cf push wfh

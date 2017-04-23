all: deploy

export PATH := bin:$(PATH)

cf:
	wget 'https://cli.run.pivotal.io/stable?release=linux64-binary&source=github' -O cf.tar.gz
	mkdir -p bin
	tar zxvf cf.tar.gz -C bin

deploy: cf
	@cf login -a https://api.run.pivotal.io -u $(CF_USERNAME) -p $(CF_PASSWORD) -o $(CF_ORG) -s $(CF_SPACE)
	cf push adopt

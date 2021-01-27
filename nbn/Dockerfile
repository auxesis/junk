# ejson
# build an ejson binary, so the docker image works on arm
FROM golang:1.13.6-stretch as go
RUN mkdir -p /go/src/github.com/Shopify/
ADD https://github.com/Shopify/ejson/archive/v1.2.1.tar.gz /go/src/github.com/Shopify/
WORKDIR /go/src/github.com/Shopify
RUN tar zxvf v1.2.1.tar.gz
RUN mv ejson-1.2.1 ejson
WORKDIR /go/src/github.com/Shopify/ejson
RUN go get 
RUN go build -o ejson "github.com/Shopify/ejson/cmd/ejson/"

# ruby app
FROM ruby:2.6.5-stretch
RUN gem install bundler
ADD Gemfile /app/
ADD Gemfile.lock /app/
WORKDIR /app
RUN bundle install

COPY . /app
COPY --from=go /go/src/github.com/Shopify/ejson/ejson /usr/local/bundle/bin/ejson
ENTRYPOINT bundle exec ruby check_appointments.rb

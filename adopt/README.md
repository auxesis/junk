# adopt

Bot for emailing me about dogs available for adoption.

## Developing

``` bash
git clone https://github.com/auxesis/junk.git
cd junk/adopt
bundle exec foreman # launches mailcatcher, for testing emails
```

## Running

Get an API key from Morph, then run the script:

```
export MORPH_API_KEY=abcdefg
bundle exec ruby adopt.rb
```

## Deploying

`adopt` is automatically [deployed by Travis](https://travis-ci.org/auxesis/junk).

But if you're deploying locally:

```
cf push adopt
```

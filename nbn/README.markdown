# nbn

Checks available nbn provisioning appointments via Aussie Broadband.

Runs as [a GitHub action](https://github.com/auxesis/junk/blob/1d492de75c5dcb7e62147917dde1ae111aa9e8f7/.github/workflows/check_nbn_appointments.yml).


## Developing

Install dependencies with:

``` bash
bundle
```

Set up `credentials.ejson`:

``` json
{
  "_public_key": "<your public key from `ejson keygen`>",
  "nbn": {
    "mobileNumber": "<your mobile number>",
    "uniqueCode": "<your aussie broadband provisioning number>"
  },
  "pagerduty": {
    "api_key": "<your pagerduty service key>"
  }
}
```

Then run with:

``` bash
ruby check_appointments.rb
```

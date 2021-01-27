# nbn

Checks available nbn provisioning appointments via Aussie Broadband.

## Running

Ensure you have Docker installed, then run

``` bash
git clone https://github.com/auxesis/junk
cd junk/nbn
```

Add a `.env` file containing the private key to decrypt the ejson:

```
CHECK_APPOINTMENTS_PRIVATE_KEY=b1946ac92492d2347c6235b4d2611184b1946ac92492d2347c6235b4d2611184
```

Build the image:

```
make image
```

Add to your crontab:

```
*/5 * * * * docker run nbn:latest
```

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

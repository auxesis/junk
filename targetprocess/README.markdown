# targetprocess

Tools for working with Targetprocess.

Currently consists of:

- `scrape.rb` – scrapes changes to custom fields out of TP, and produces a simple report. Currently support extracting custom fields named `Work Category`.
- `lib/tp.rb` – very lightweight API client for working with the TP API.

## Setup

git clone this repo, and run `bundle install`.

Add secrets to `.env`:

``` bash
TP_SUBDOMAIN="foobarbaz"        # The subdomain of your tpondemand.com instance
TP_TOKEN="ccc16cba59abc123def4" # API access token, found on your user account in TP
TP_SESSION_COOKIE="cookie: ..." # Session cookie from an authenticated browser session
```

You can get the TP session cookie by:

1. Navigating to your TP instance
1. Popping the web inspector
1. Going to the Network tab
1. Toggling filtering to XHR
1. Selecting the cookie with a triple click:
   ![TP web inspector](https://user-images.githubusercontent.com/12306/86315825-9b879580-bc6e-11ea-8c18-7cac29c3cdb4.gif)
1. Copy-pasting the cookie into `.env`

## Run

Run the scraper with:

```
bundle exec ruby scrape.rb
```

## Known issues

- Uses Aruba to shell out to cURL. You might run into file descriptor limits in your terminal. Fix them with `ulimit -S -n 8096`.

## Setup

```
git clone ...
cd recognition
bundle
```

Generate a Slack API token for the target workspace, and add it to `.env`:

```
SLACK_API_TOKEN=aoesntaoesntsntaoudsidsanoetsnt
```

## Usage

Add the people you want to scrape profile images for to `people.txt`

```
Ada Lovelace
# comments are ignored
Grace Hopper



# so is whitespace
```

Scrape their profile images from Slack:

```
bundle exec ruby scraper.rb
```

This will:

 - write the data to `data.sqlite`
 - write a file per profile photo in `avatars/`

Ensure you have ImageMagick installed, then generate the montage:

```
sh -x montage.sh
```

This will generate and open the montage at `montage.png`

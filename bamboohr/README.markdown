# BambooHR tools

## Setup

Clone and set up the repo:

```
git clone https://github.com/amandavarella/junk.git
cd junk/bamboohr
bundle
```

Add a `.env` with your BambooHR API key:

``` bash
BAMBOOHR_SUBDOMAIN=mycorp
BAMBOOHR_API_KEY=aa85a19f9450a9a4f90062c3f127612e5011abc7ea
```

Scrape the org chart from BambooHR:

1. Go to https://mycorp.bamboohr.com/employees/orgchart.php
1. Click on Export \  `Unformatted.csv`
1. Rename the file to `employees.json`, and leave it under the  `bamboohr` directory


## `report_time_off.rb`

Generates a report of the days worked by folks under someone in the org chart:

``` bash
ruby report_time_off.rb --under-user 'Ray Grasso'
```

Takes into account public holidays too.

You can specify a week to query:

``` bash
ruby report_time_off.rb --under-user 'Ray Grasso' --start-date 2019-01-14 --weeks 10
```

For dates in the past, this will report leave taken.

For dates in the future, this will report booked leave.


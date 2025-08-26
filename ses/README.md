
## `analyse_detailed_incidents_listing.rb`

Generate a report on jobs for a given period, covering:

- Number of jobs referred

To get the data:

1. Visit https://beacon.ses.nsw.gov.au/Reports
2. Select the "Detailed Incident Listing" report
3. Set a date range, most likely "Custom Range"
   - Starting previous Monday @ 19:00
   - Finishing current Monday @ 18:59
4. Click blue "Generate" button.

   This will produce a CSV with a filename like `DetailedIncidentListing_19-08-2025_25-08-2025.csv`

Then run the report:

```bash
ruby analyse_detailed_incidents_listing.rb DetailedIncidentListing_19-08-2025_25-08-2025.csv
```

## `analyse_member_activity.rb`

Generate a report on jobs for a given period, covering:

- Number of teams active on storm/flood jobs
- Number of members active on storm/flood jobs
- Number of members who went out on multiple days

To get the data:

1. Visit https://beacon.ses.nsw.gov.au/Reports
2. Select the "Member Activity Report" report
3. Set a date range, most likely "Custom Range"
   - Starting previous Monday @ 19:00
   - Finishing current Monday @ 18:59
4. Click blue "Generate" button.

   This will produce a CSV with a filename like `MemberActivity_19-08-2025_25-08-2025.csv`

Then run the report:

```bash
ruby analyse_member_activity.rb MemberActivity_19-08-2025_25-08-2025.csv
```

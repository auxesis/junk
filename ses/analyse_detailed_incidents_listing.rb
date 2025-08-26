#!/usr/bin/env ruby

# Generate a report on jobs for a given period.
#
# To get the data:
#
# 1. Visit https://beacon.ses.nsw.gov.au/Reports
# 2. Select the "Detailed Incident Listing" report
# 3. Set a date range, most likely "Custom Range"
#    - Starting previous Monday @ 19:00
#    - Finishing current Monday @ 18:59
# 4. Click blue "Generate" button
# 5. Pass the CSV as an argument to this script, with a filename like:
#    DetailedIncidentListing_19-08-2025_25-08-2025.csv

require "csv"
require "pry"

filename = ARGV.first

unless filename && File.exist?(filename)
  puts "Usage: #{File.basename($PROGRAM_NAME)} <csv_file>"
  exit 1
end

data = CSV.read(filename, headers: true).map(&:to_hash)

referred = data.select { |i| i["Referred"] == "Yes" }
puts "Referred: #{referred.size}"

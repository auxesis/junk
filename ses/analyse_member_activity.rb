#!/usr/bin/env ruby

# Generate a report on jobs for a given period.
#
# To get the data:
#
# 1. Visit https://beacon.ses.nsw.gov.au/Reports
# 2. Select the "Member Activity Report" report
# 3. Set a date range, most likely "Custom Range"
#    - Starting previous Monday @ 19:00
#    - Finishing current Monday @ 18:59
# 4. Click blue "Generate" button
# 5. Pass the CSV as an argument to this script, with a filename like:
#    MemberActivity_19-08-2025_25-08-2025.csv

require "csv"

filename = ARGV.first

unless filename && File.exist?(filename)
  puts "Usage: #{File.basename($PROGRAM_NAME)} <csv_file>"
  exit 1
end

data = CSV.read(filename, headers: true).map(&:to_hash)

by_type = data.group_by { |d| d["Incident Type/NIT Type"] }

# teams active on storm/flood jobs
teams_active = data.select { |d| d["Incident Type/NIT Type"] =~ /(FR|Flood Misc|Storm)/ }.group_by { |d| d["Team name/Session Name"] }
puts "Teams active: #{teams_active.size}"

# members active on storm/flood jobs
members_active = data.select { |d| d["Incident Type/NIT Type"] =~ /(FR|Flood Misc|Storm)/ }.group_by { |d| d["Member Code"] }
puts "Members active: #{members_active.size}"

# members who went out on multiple days
members_active_on_multiple_days = data.select { |d|
  d["Incident Type/NIT Type"] =~ /(FR|Flood Misc|Storm)/
}.group_by { |d|
  d["Member Code"]
}.select { |member_id, incidents|
  teams = incidents.map { |i|
    i["Team name/Session Name"]
  }.sort.uniq.size > 1
}
puts "Members active on multiple days: #{members_active_on_multiple_days.size}"
members_active_on_multiple_days.each do |member, incidents|
  puts " * #{incidents.first["FirstName"]} #{incidents.first["LastName"]}"
end

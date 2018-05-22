require 'json'
require 'uri'

if ARGV.first == nil || ARGV.first == '-'
  lines = STDIN.readlines
else
  lines = File.readlines(ARGV.first)
end

target_line = lines.grep(/window\["SNAPSHOT"\]/).first
escaped_json = target_line[/JSON.parse\(unescape\("(.*)"/,1]
json = URI.decode(escaped_json)
data = JSON.parse(json)

data['Action'].each do |action|
  puts "#{action['who']} to #{action['what']}"
end

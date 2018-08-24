# frozen_string_literal: true

require 'nokogiri'
require 'json'
require 'cgi'

lines = if ARGV.first.nil? || ARGV.first == '-'
          STDIN.readlines
        else
          File.readlines(ARGV.first)
        end

target_line = lines.grep(/window\["SNAPSHOT"\]/).first
escaped_json = target_line[/JSON.parse\(unescape\("(.*)"/, 1]
json = CGI.unescape(escaped_json)
data = JSON.parse(json)

data['Action'].each do |action|
  what = Nokogiri::HTML(action['what']).text.downcase
  puts "#{action['who']} to #{what}"
end

# frozen_string_literal: true

require "csv"

lines = if ARGV.first.nil? || ARGV.first == "-"
          STDIN.readlines
        else
          File.readlines(ARGV.first)
        end

# first four lines are header :-/
contents = lines[4..-1].join
rows = CSV.parse(contents, headers: true)

if ARGV.grep("--output-notion").any?
  rows.sort_by { |row| row["Who"].strip }.each do |action|
    puts "###\n"
    puts action["What"].strip.downcase.capitalize
    puts action["Who"].strip
    puts
  end
else
  puts ":motorway: Here are the actions from the retro:\n\n"

  rows.sort_by { |row| row["Who"].strip }.each do |action|
    puts ":rocket: *#{action["Who"].strip}* to _#{action["What"].strip.downcase}_"
  end
end

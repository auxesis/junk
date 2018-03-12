# frozen_string_literal: true

require 'bamboozled'
require 'active_support/core_ext/integer'
require 'pry'
require 'optparse'
require 'dotenv'
Dotenv.load

def parse!
  options = {}
  OptionParser.new do |opts|
    opts.banner = "Usage: #{$PROGRAM_NAME} [options]"

    opts.on('-s', '--sprint NUMBER', 'Sprint number to fetch leave for') do |n|
      options[:sprint_number] = n.to_i
    end
  end.parse!

  unless options[:sprint_number]
    puts 'Missing argument --sprint'
    exit(1)
  end

  options
end

# Monkey patch bug in Skookum/bamboozled
class Array
  def with_indifferent_access
    self
  end
end

class Sprint
  def self.sprints
    return @sprints if @sprints

    first_day_of_first_sprint = (epoch.to_date.end_of_week + 1)

    @sprints = {}
    (1..26).each do |i|
      @sprints[i] = {
        start: (first_day_of_first_sprint + (14 * i) - 14).to_time.beginning_of_day,
        finish: (first_day_of_first_sprint + (14 * i) - 1).to_time.end_of_day
      }
    end
    @sprints
  end

  def self.epoch(year: '2017')
    Date.parse("#{year}-07-01").to_time.beginning_of_day
  end

  def self.[](number)
    boundaries = sprints[number]
    Sprint.new(start: boundaries[:start], finish: boundaries[:finish])
  end

  attr_reader :start, :finish

  def initialize(start:,finish:)
    @start = start
    @finish = finish
  end
end

def main
  options = parse!
  params = {
    subdomain: ENV['BAMBOOHR_SUBDOMAIN'],
    api_key: ENV['BAMBOOHR_API_KEY']
  }

  client = Bamboozled.client(params)
  sprint = Sprint[options[:sprint_number]]
  time_off = client.time_off.whos_out(sprint.start, sprint.finish)
  time_off.sort_by { |e| e['name'] }.each do |entry|
    puts [ entry['name'], entry['start'], entry['end'] ].join("\t")
  end
end

main if $PROGRAM_NAME == __FILE__

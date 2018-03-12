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
    attrs = {
      number: number,
      start: boundaries[:start],
      finish: boundaries[:finish],
    }
    Sprint.new(attrs)
  end

  attr_reader :number, :start, :finish

  def initialize(number:,start:,finish:)
    @number = number
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
  puts "### Sprint #{sprint.number} (#{sprint.start.to_date}-#{sprint.finish.to_date})"
  time_off = client.time_off.whos_out(sprint.start, sprint.finish)

  sprint_range = (sprint.start.to_date..sprint.finish.to_date).to_a
  leave_totals = {}
  time_off.each do |entry|
    # set the leave balance for the person to zero
    leave_totals[entry['name']] ||= 0
    # calculate the number of work days the person has been off
    leave_range = (Date.parse(entry['start'])..Date.parse(entry['end'])).to_a
    days_off = leave_range & sprint_range
    work_days_off = days_off.reject {|d| d.saturday? || d.sunday? }
    # increment the total
    leave_totals[entry['name']] += work_days_off.size
  end

  leave_totals.sort_by { |name,total| name }.each do |name,total|
    puts [ name, total ].join("\t")
  end
end

main if $PROGRAM_NAME == __FILE__

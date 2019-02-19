# frozen_string_literal: true

$LOAD_PATH << File.join(File.expand_path(__dir__), 'lib')

require 'org_chart'
require 'bamboozled'
require 'active_support/core_ext/date'
require 'active_support/core_ext/integer'
require 'optparse'
require 'dotenv'
Dotenv.load

# rubocop:disable Metrics/MethodLength
def parse!
  options = {}
  OptionParser.new do |opts|
    opts.banner = "Usage: #{$PROGRAM_NAME} [options]"

    opts.on('-u', '--under-user NAME', 'What user to generate report under') do |u|
      options[:under_user] = u
    end

    opts.on('-s', '--start-date DATE', 'Start date of the week to report on') do |d|
      options[:start_date] = Date.parse(d).beginning_of_week
    end
  end.parse!

  options[:start_date] ||= Date.today.beginning_of_week
  options[:finish_date] = options[:start_date] + 4

  unless options[:under_user]
    puts 'Missing argument --under-user'
    exit(1)
  end

  options
end
# rubocop:enable Metrics/MethodLength

# Monkey patch bug in Skookum/bamboozled
class Array
  def with_indifferent_access
    self
  end
end

def reports(name)
  memo = [OrgChart.lookup(name).first]
  OrgChart.reports(name).each do |report|
    memo << reports(report[:name])
  end
  memo.flatten.uniq
end

def responsible_for?(reports:, person:)
  reports.any? { |r| r[:id] == person['employeeId'] }
end

def main
  # setup
  options = parse!
  params = {
    subdomain: ENV['BAMBOOHR_SUBDOMAIN'],
    api_key: ENV['BAMBOOHR_API_KEY']
  }
  client = Bamboozled.client(params)

  hash = JSON.parse(File.read('employees.json'))
  OrgChart.build_tree_from_hash(hash)

  # get the people we need to produce a report for
  people = reports(options[:under_user])

  timeframe = OpenStruct.new(start: options[:start_date], finish: options[:finish_date])
  all_leave = client.time_off.whos_out(timeframe.start, timeframe.finish)

  puts "\t#{timeframe.finish}"

  timeframe_range = (timeframe.start..timeframe.finish).to_a
  work_days = {}

  # deduct leave
  people.each do |person|
    work_days[person[:name]] = 5
    time_off = all_leave.select { |e| e['employeeId'] == person[:id] }

    time_off.each do |entry|
      leave_range = (Date.parse(entry['start'])..Date.parse(entry['end'])).to_a
      days_off = leave_range & timeframe_range
      work_days_off = days_off.reject { |d| d.saturday? || d.sunday? }
      work_days[person[:name]] -= work_days_off.size
    end
  end

  # deduct holidays
  holidays = all_leave.select { |l| l['type'] == 'holiday' }
  holidays.each do
    work_days.each do |name, count|
      work_days[name] -= 1 unless count <= 0
    end
  end

  # print the totals
  work_days.sort_by { |name, _| name }.each do |name, count|
    puts [name, count].join("\t")
  end
end

main if $PROGRAM_NAME == __FILE__

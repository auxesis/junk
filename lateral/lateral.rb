# frozen-string-literal: true

require 'bamboozled'
require 'configatron'
require 'dotenv'
require 'tree'
require 'pry'
require 'fuzzy_match'
require 'slack-ruby-client'
require 'json'

Dotenv.load

configatron.bamboohr.subdomain = ENV['BAMBOOHR_SUBDOMAIN']
configatron.bamboohr.api_key = ENV['BAMBOOHR_API_KEY']

Node = Tree::TreeNode

def json
  JSON.parse(File.read('employees.json'))
end

def directory
  @directory ||= {}
end

def add_to_directory(attrs)
  name = attrs['name'].strip
  directory[name] = {
    id: attrs['id'],
    job_title: attrs.dig('data','jInfo','job_title'),
    direct_reports: attrs.dig('data', 'directReports') > 0
  }
  return name
end

def build_node(attrs)
  name = attrs['name'].strip
  add_to_directory(attrs)
  node = Node.new(name)
  build_tree(node, attrs['children'])
  node
end

def build_tree(parent, children)
  children.each { |attrs| parent << build_node(attrs) }
end

def dag
  return @root if @root
  @root = build_node(json)
  return @root
end

def bamboohr
  @client ||= Bamboozled.client(configatron.bamboohr.to_hash)
end

def index
  @index ||= (dag && FuzzyMatch.new(directory.keys))
end

def find_in_tree(name)
  dag.find { |n| n.name == name }
end

def parentage(name)
  find_in_tree(name).parentage&.map(&:name)&.reverse.map { |n|
    [n, directory[n]]
  }
end

def children(name)
  find_in_tree(name).children&.map(&:name).map { |n|
    [n, directory[n]]
  }
end

def lookup(name)
  index.find_all(name, threshold: 0.5).map { |n| [ n, directory[n] ] }
end

def format_name(name, attrs)
  base = [ name, attrs[:job_title] ].join(' – ')
  base += ' :small_blue_diamond:' if attrs[:direct_reports]
  return base
end

Slack.configure do |config|
  config.token = ENV['SLACK_API_TOKEN']
end

client = Slack::RealTime::Client.new

client.on :message do |data|
  client.typing channel: data.channel
  case data.text
  when /^find (?<name>.+)$/i
    name = $~[:name]
    text = lookup(name).map { |name, attrs|
      [ name, attrs[:job_title] ].join(' – ')
    }.join("\n")
    client.message(channel: data.channel, text: text)
  when /^chart (?<name>.+)$/i
    name = lookup($~[:name]).first.first
    text = []
    text << parentage(name).map { |name, attrs| ':arrow_up: ' + format_name(name, attrs) }
    text << ':star: ' + format_name(name, directory[name])
    text << children(name).map { |name, attrs| ':arrow_right_hook: ' + format_name(name, attrs) }
    client.message(channel: data.channel, text: text.join("\n"))
  when /^debug.+/i
    p data
    client.message(channel: data.channel, text: data.inspect)
  end
end

def main
  client.start!
end

main if $PROGRAM_NAME == __FILE__


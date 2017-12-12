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

class OrgChart
  class << self
    attr_accessor :tree

    def bosses(id)
      find_in_tree(id)&.parentage&.map(&:name)&.reverse.map { |n|
        [n, directory[n]]
      }
    end

    def reports(id)
      find_in_tree(id).children&.map(&:name).map { |n|
        [n, directory[n]]
      }
    end

    def lookup(name, threshold: 0.5)
      index.find_all_with_score(name, threshold: threshold).map do |name, score|
        directory[name].merge(name: name, score: score)
      end
    end

    def directory
      @directory ||= {}
    end

    def format(person: )
      base = [ person[:name], person[:job_title] ].join(' – ')
      base += ' :small_blue_diamond:' if person[:direct_reports]
      return base
    end

    def build_tree_from_hash(hash)
      @directory&.clear
      @index = nil
      @tree = build_node(hash)
    end

    private

    def add_to_directory(attrs)
      name = attrs['name'].strip
      directory[name] = {
        id: attrs['id'],
        job_title: attrs.dig('data','jInfo','job_title'),
        direct_reports: attrs.dig('data', 'directReports').positive?
      }
    end

    def index
      @index ||= FuzzyMatch.new(directory.keys)
    end

    def find_in_tree(id)
      tree.find { |n| n.name == id }
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
  end
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
    text << OrgChart.bosses(name).map { |person| ':arrow_up: ' + OrgChart.format_name(person) }
    text << ':star: ' + OrgChart.format_name(directory[name])
    text << OrgChart.reports(name).map { |person| ':arrow_right_hook: ' + OrgChart.format_name(person) }
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


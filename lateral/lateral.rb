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
      find_in_tree(id)&.parentage&.map(&:name)&.reverse.map do |name|
        directory[name].merge(name: name)
      end
    end

    def reports(id)
      find_in_tree(id).children&.map(&:name).map do |name|
        directory[name].merge(name: name)
      end
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

module Lateral
  class BaseCommand
    class << self
      def usage
        raise NotImplementedError
      end

      def matcher
        raise NotImplementedError
      end

      def run(client,data)
        raise NotImplementedError
      end

      def commands
        descendants
      end
    end
  end

  class FindCommand < BaseCommand
    class << self
      def matcher
        /^find (?<name>.+)$/i
      end

      def run(client, data)
        name = data.text.match(matcher)['name']
        results = OrgChart.lookup(name)
        if results.any?
          text = OrgChart.lookup(name).map { |person|
            OrgChart.format(person: person)
          }.join("\n")
        else
          text = "Sorry, I couldn't find anyone matching _#{name}_ in the org chart"
        end
        client.message(channel: data.channel, text: text)
      end

      def usage
        "`find <name>` – List all people in the org chart whose names match"
      end
    end
  end

  class ChartCommand < BaseCommand
    class << self
      def matcher
        /^chart (?<name>.+)$/i
      end

      def run(client, data)
        name = data.text.match(matcher)['name']
        text = []
        text << OrgChart.bosses(name).map { |person| ':arrow_up: ' + OrgChart.format(person: person) }
        text << ':star: ' + OrgChart.format(person: OrgChart.directory[name].merge(name: name))
        text << OrgChart.reports(name).map { |person| ':arrow_right_hook: ' + OrgChart.format(person: person) }
        client.message(channel: data.channel, text: text.join("\n"))
      end

      def usage
        "`chart <name>` – Show a person's reporting lines all the way to the top"
      end
    end
  end

  class DebugCommand < BaseCommand
    class << self
      def matcher
        /^debug.*/i
      end

      def run(client, data)
        client.message(channel: data.channel, text: data.inspect)
      end

      def usage
        "`debug` – Echos internal representation of the message back"
      end
    end
  end

  class HelpCommand < BaseCommand
    class << self
      def matcher
        /^help.*$/i
      end

      def run(client, data)
        text = BaseCommand.commands.map(&:usage).sort.join("\n")
        client.message(channel: data.channel, text: text)
      end

      def usage
        "`help` – How to use Lateral (this message)"
      end
    end
  end

  class Bot
    class << self
      def handle_message(client, data)
        command = BaseCommand.commands.detect { |command| data.text =~ command.matcher }
        if command
          command.run(client, data)
        else
          client.message(channel: data.channel, text: "Sorry, I don't understand. Try typing `help`")
        end
      end

      def client
        @client ||= Slack::RealTime::Client.new
      end

      def run
        client.on :message do |data|
          client.typing channel: data.channel
          Lateral::Bot.handle_message(client, data)
        end

        client.start!
      end
    end
  end
end

Slack.configure do |config|
  config.token = ENV['SLACK_API_TOKEN']
end

Lateral::Bot.run if $PROGRAM_NAME == __FILE__

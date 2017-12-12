# frozen_string_literal: true

require 'spec_helper'
require 'ostruct'

class MockSlackClient
  attr_accessor :messages

  def initialize
    @messages = []
  end

  def message(opts={})
    @messages << opts
  end
end

describe Lateral do
  include_context 'orgchart'

  let(:client) { MockSlackClient.new }

  describe Lateral::FindCommand do
    let(:target) { OrgChart.directory.keys.last }
    let(:data) { OpenStruct.new(text: "find #{target}", channel: 'test') }

    it 'returns a list of matching names' do
      Lateral::Bot.handle_message(client, data)
      expect(client.messages.first[:text]).to include(target)
    end

    context 'when there are no results' do
      let(:data) { OpenStruct.new(text: "find #{Time.now}", channel: 'test') }

      it 'explains there are no results' do
        Lateral::Bot.handle_message(client, data)
        expect(client.messages.first[:text]).to match(/sorry.*couldn't find/i)
      end
    end
  end

  describe Lateral::ChartCommand do
    let(:target) { OrgChart.directory.keys.last }
    let(:data) { OpenStruct.new(text: "chart #{target}", channel: 'test') }

    it 'returns a list of matching names' do
      Lateral::Bot.handle_message(client, data)
      expect(client.messages.first[:text]).to include(target)
    end
  end

  describe 'usage' do
    context 'when no commands match' do
      let(:data) { OpenStruct.new(text: "foobarbaz", channel: 'test') }
      it 'prompts to use the help command' do
        Lateral::Bot.handle_message(client, data)
        expect(client.messages.first[:text]).to match(/`help`/)
      end
    end

    context 'when help is asked for' do
      let(:data) { OpenStruct.new(text: 'help', channel: 'test') }
      let(:usages) { Lateral::BaseCommand.commands.map(&:usage) }

      it 'displays usage information for all commands', :aggregate_failures do
        Lateral::Bot.handle_message(client, data)

        usages.each do |usage|
          expect(client.messages.first[:text]).to include(usage)
        end
      end
    end
  end
end

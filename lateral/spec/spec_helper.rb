# frozen_string_literal: true

require_relative('../lateral')
require 'pry'
require 'webmock/rspec'
require 'addressable'
require 'vcr'

VCR.configure do |c|
  c.cassette_library_dir = 'spec/vcr_cassettes'
  c.hook_into :webmock
end

RSpec.configure do |config|
  # Use color not only in STDOUT but also in pagers and files
  config.tty = true
end

RSpec.shared_context 'orgchart' do
  def person
    {
      'id' => 1,
      'name' => Faker::Name.name,
      'data' => {
        'img' => Faker::Internet.url,
        'jInfo' => { 'job_title' => Faker::Name.title },
        'directReports' => 1
      },
      'children' => []
    }
  end

  let(:hash) {
    root = person
    root['children'] += [ person, person, person]
    root['children'].each do |child|
      child['children'] += [ person, person, person, person ]
    end
    root
  }

  before(:each) do
    OrgChart.build_tree_from_hash(hash)
  end
end

def all_requests
  WebMock::RequestRegistry.instance.requested_signatures.hash.keys
end

def all_request_bodies
  all_requests.map { |r| JSON.parse(r.body) }
end

def puts(*args); end

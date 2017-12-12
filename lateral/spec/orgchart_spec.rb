# frozen_string_literal: true

require 'spec_helper'
require 'faker'

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

describe OrgChart do
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

  describe '.lookup' do
    context 'single term' do
      it 'returns a list of matching users' do
        expect(OrgChart.lookup(hash['name']).any?).to be true
      end
    end

    context 'with filters' do
      let(:threshold) { 0.2 }

      it 'returns a list of matching users' do
        expect(OrgChart.lookup(hash['name'], threshold: 0.0).size > 1).to be true
      end

      it 'filters based on score', :aggregate_failures do
        results = OrgChart.lookup(hash['name'], threshold: threshold)
        results.each do |result|
          expect(result[:score] >= threshold).to be true
        end
      end
    end
  end

  describe '.bosses' do
    it 'provides a list of bosses up the chain' do
      target = OrgChart.directory.keys.last
      expect(OrgChart.bosses(target).size > 0).to be true
    end
  end

  describe '.reports' do
    it 'provides a list of direct reports' do
      target = OrgChart.directory.keys[-5]
      expect(OrgChart.reports(target).size > 0).to be true
    end
  end

  describe '.directory' do
    let(:keys) { %i[id job_title direct_reports] }
    it 'provides a hash of people and attributes', :aggregate_failures do
      OrgChart.directory.each do |name, attrs|
        expect(keys.all? { |k| attrs.has_key?(k) }).to be true
      end
    end
  end

  describe '.format' do
    let(:name) { 'John Doe' }
    let(:job_title) { 'Mortician' }
    let(:report) { { name: name, job_title: job_title, direct_reports: false } }
    let(:manager) { person.merge(direct_reports: true) }
    let(:manager_marker) { ':small_blue_diamond:' }

    it 'prints name displayable for Slack' do
      expect(OrgChart.format(person: report)).to match(/#{name}.+#{job_title}/)
    end

    context 'when the person is a people manager' do
      it 'denotes the person is a manager' do
        expect(OrgChart.format(person: manager)).to match(manager_marker)
      end
    end
  end
end

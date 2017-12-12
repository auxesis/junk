# frozen_string_literal: true

require 'spec_helper'
require 'faker'

describe OrgChart do
  include_context 'orgchart'

  describe '#lookup' do
    context 'single term' do
      it 'returns a list of matching users' do
        expect(OrgChart.lookup(hash['name']).any?).to be true
      end

      it 'returns an array of hashes' do
        results = OrgChart.lookup(hash['name'])
        results.each do |result|
          expect(result.is_a?(Hash)).to be true
        end
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

  describe '#bosses' do
    let(:target) { OrgChart.directory.keys.last }

    it 'provides a list of bosses up the chain' do
      expect(OrgChart.bosses(target).size > 0).to be true
    end

    it 'returns an array of hashes' do
      results = OrgChart.bosses(target)
      results.each do |result|
        expect(result.is_a?(Hash)).to be true
      end
    end

    context 'when querying the top of the tree' do
      let(:target) { OrgChart.directory.keys.first }

      it 'returns nothing' do
        expect(OrgChart.bosses(target).empty?).to be true
      end
    end
  end

  describe '#reports' do
    let(:target) { OrgChart.directory.keys[-5] }

    it 'provides a list of direct reports' do
      expect(OrgChart.reports(target).size > 0).to be true
    end

    it 'returns an array of hashes' do
      results = OrgChart.reports(target)
      results.each do |result|
        expect(result.is_a?(Hash)).to be true
      end
    end
  end

  describe '#directory' do
    let(:keys) { %i[id job_title direct_reports] }
    it 'provides a hash of people and attributes', :aggregate_failures do
      OrgChart.directory.each do |name, attrs|
        expect(keys.all? { |k| attrs.has_key?(k) }).to be true
      end
    end
  end

  describe '#format' do
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

require_relative '../time_off'

describe Sprint do
  let(:number) { 17 }
  describe '#[]' do
    it 'returns a Sprint object' do
      sprint = Sprint[number]
      expect(sprint.class).to eq(Sprint)
    end
  end

  describe 'first sprint' do
    let(:years) { 2015..2030 }

    it 'starts on the first Monday' do
      years.each do |year|
        Sprint.year = year
        sprint = Sprint[1]
        expect((sprint.start.to_date - Sprint.epoch.to_date).to_i).to be <= 6
      end
    end
  end

  describe '.start' do
    let(:numbers) { (1..26) }

    it 'is a Monday' do
      numbers.each do |n|
        sprint = Sprint[n]
        expect(sprint.start.monday?).to be true
      end
    end

    it 'is the first possible second of that sprint' do
      numbers.each do |n|
        sprint = Sprint[n]
        expect(sprint.start).to eq(sprint.start.beginning_of_day)
      end
    end
  end

  describe '.finish' do
    let(:numbers) { (1..26) }

    it 'is a Sunday' do
      numbers.each do |n|
        sprint = Sprint[n]
        expect(sprint.finish.sunday?).to be true
      end
    end

    it 'is the last possible second of that sprint' do
      numbers.each do |n|
        sprint = Sprint[n]
        expect(sprint.finish).to eq(sprint.finish.end_of_day)
      end
    end
  end
end

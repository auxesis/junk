# frozen-string-literal: true

require 'csv'
require 'org_chart/json'
require 'org_chart/csv'

# Organisation tree and directory of people
class OrgChart
  class << self
    attr_accessor :engine

    %w[from bosses reports lookup directory orphans to_hash reset!].each do |name|
      class_eval <<-"RUBY", __FILE__, __LINE__ + 1
        def #{name}(*args)
          engine.#{name}(*args)
        end
      RUBY
    end
  end
end

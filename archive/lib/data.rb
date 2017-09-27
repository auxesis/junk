# frozen-string-literal: true

require 'json'
require 'pry'
require 'sequel'

DB = Sequel.sqlite('data.sqlite')

# Trello lists
class List < Sequel::Model
  set_primary_key :id
  one_to_many :cards
end

# Trello cards
class Card < Sequel::Model
  set_primary_key :id
  many_to_one :list
  one_to_many :actions

  plugin :serialization, :json, :json
  alias attrs json
  def method_missing(method_name)
    attrs[method_name.to_s] || attrs[method_name] || super
  end

  def respond_to_missing?(method_name)
    attrs[method_name.to_s] || attrs[method_name]
  end
end

# Trello card actions
class Action < Sequel::Model
  set_primary_key :id
  many_to_one :card

  def date
    Time.parse(attrs['date']) if attrs['date']
  end

  plugin :serialization, :json, :json
  alias attrs json
  def method_missing(method_name)
    attrs[method_name.to_s] || attrs[method_name] || super
  end

  def respond_to_missing?(method_name)
    attrs[method_name.to_s] || attrs[method_name]
  end
end

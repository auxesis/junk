#!/usr/bin/env ruby

require 'json'
require 'pry'
require 'sequel'

DB = Sequel.sqlite('data.sqlite')

class Card < Sequel::Model
  set_primary_key :id
  one_to_many :actions
end

class Action < Sequel::Model
  set_primary_key :id
  many_to_one :card

  plugin :serialization, :json, :json
end

binding.pry

updates = Action.all.select {|a| a.attrs['type'] == 'updateCard' }

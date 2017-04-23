require 'rufus-scheduler'
require 'httparty'
require 'mail'
require 'tilt'
require 'redcarpet'

ENV['TZ'] = 'Australia/Sydney'

Mail.defaults do
  delivery_method :smtp, address: 'localhost', port: 1025
end

def animals
  query = {
    query: "select name,description,breed,id,link from data where type = 'dog' and (breed like '%labrador%' or breed like '%poodle%') and state = 'New South Wales' and scraped_at > date('now', '-3 days');",
    key: ENV['MORPH_API_KEY'],
  }
  url = 'https://api.morph.io/auxesis/petrescue_scraper/data.json'
  HTTParty.get(url, :query => query)
end

def mail(animals)
  puts "[info] There are #{animals.size} animals matching the query"
  if animals.size > 0
    recipients.each do |recipient|
      message = Mail.new
      message.charset = 'UTF-8'
      message.from    = 'alerts@petrescue.com.au'
      message.to      = recipient
      message.subject = "#{animals.size} new animals on Pet Rescue"
      message.text_part = text_part(:animals => animals)
      message.html_part = html_part(:animals => animals)
      message.deliver
    end
  else
    puts '[info] Skipping sending an email because no animals match query'
  end
end

def recipients
  ENV['RECIPIENTS'].split(',')
end

def validate_recipients!
  if ENV['RECIPIENTS'].nil?
    puts '[info] You must specify RECIPIENTS to receive the alerts'
    puts '[info] Exiting!'
    exit(2)
  end
end

def text_part(opts={})
  part = Mail::Part.new
  part.content_type 'text/plain; charset=UTF-8'
  template = Tilt::ERBTemplate.new('text.erb')
  part.body = template.render(self, opts)

  return part
end

def html_part(opts={})
  part = Mail::Part.new
  part.content_type 'text/html; charset=UTF-8'
  template = Tilt::HamlTemplate.new('html.haml')
  part.body = template.render(self, opts)

  return part
end

def main
  validate_recipients!

  scheduler = Rufus::Scheduler.new
  scheduler.cron '0 18 * * * Australia/Sydney' do
    begin
      mail(animals)
    rescue => e
      p e
    end
  end
  scheduler.join
end

main()

binding.pry

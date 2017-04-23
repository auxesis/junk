require 'rufus-scheduler'
require 'httparty'
require 'mail'
require 'tilt'
require 'redcarpet'

ENV['TZ'] = 'Australia/Sydney'

def sendgrid
  return @sendgrid_credentials if @sendgrid_credentials
  if ENV['VCAP_SERVICES']
    vcap_services = JSON.parse(ENV['VCAP_SERVICES'])
    if vcap_services['sendgrid']
      @sendgrid_credentials = vcap_services['sendgrid'].first['credentials']
      return @sendgrid_credentials
    end
  end
  return nil
end

def setup_mail!
  if sendgrid
    credentials = {
      :address => sendgrid['hostname'],
      :port    => '587',
      :user_name => sendgrid['username'],
      :password  => sendgrid['password'],
      :authentication       => :plain,
      :enable_starttls_auto => true,
    }
  else
    credentials = { address: 'localhost', port: 1025 }
  end
  puts "[debug] Mail settings: #{credentials}"
  Mail.defaults do
    delivery_method :smtp, credentials
  end
end

def animals
  query = {
    query: "select name,description,breed,id,link from data where type = 'dog' and (breed like '%labrador%' or breed like '%poodle%') and state = 'New South Wales' and scraped_at > date('now', '-3 days');",
    key: morph_api_key,
  }
  url = 'https://api.morph.io/auxesis/petrescue_scraper/data.json'
  response = HTTParty.get(url, :query => query)
  if response.ok?
    response
  else
    puts "[debug] unexpected response: #{response.inspect}"
    []
  end
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
  ENV['RECIPIENTS'] ? ENV['RECIPIENTS'].split(',') : []
end

def morph_api_key
  ENV['MORPH_API_KEY']
end

def validate_recipients!
  if recipients.size < 1
    puts '[info] You must specify RECIPIENTS to receive the alerts'
    puts '[info] Example: RECIPIENTS=me@hello.example,you@hello.example'
    puts '[info] Exiting!'
    exit(2)
  end
end

def validate_morph_api_key!
  unless morph_api_key
    puts '[info] You must specify MORPH_API_KEY to collect data from Morph'
    puts '[info] Example: MORPH_API_KEY=abcdefg'
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
  validate_morph_api_key!
  setup_mail!

  scheduler = Rufus::Scheduler.new
  scheduler.cron '*/2 * * * * Australia/Sydney' do
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

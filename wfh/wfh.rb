require 'google/apis/calendar_v3'
require 'googleauth'
require 'googleauth/stores/file_token_store'
require 'fileutils'
require 'slack-notifier'
require 'rufus-scheduler'

OOB_URI = 'urn:ietf:wg:oauth:2.0:oob'
APPLICATION_NAME = 'Google Calendar API Ruby Quickstart'
CLIENT_SECRETS_PATH = 'client_secret.json'
CREDENTIALS_PATH = File.join('wfh-calendar.yaml')
SCOPE = Google::Apis::CalendarV3::AUTH_CALENDAR_READONLY

##
# Ensure valid credentials, either by restoring from the saved credentials
# files or intitiating an OAuth2 authorization. If authorization is required,
# the user's default browser will be launched to approve the request.
#
# @return [Google::Auth::UserRefreshCredentials] OAuth2 credentials

def credentials(authorizer)
  user_id = 'default'
  credentials = authorizer.get_credentials(user_id)
  return credentials if credentials

  url = authorizer.get_authorization_url(base_url: OOB_URI)
  puts "Open the following URL in the browser and enter the resulting code after authorization"
  puts url
  code = gets
  opts = { user_id: user_id, code: code, base_url: OOB_URI }
  authorizer.get_and_store_credentials_from_code(opts)
end

def authorize
  FileUtils.mkdir_p(File.dirname(CREDENTIALS_PATH))
  client_id = Google::Auth::ClientId.from_file(CLIENT_SECRETS_PATH)
  token_store = Google::Auth::Stores::FileTokenStore.new(file: CREDENTIALS_PATH)
  authorizer = Google::Auth::UserAuthorizer.new(client_id, SCOPE, token_store)
  credentials(authorizer)
end

def whereami
  # Initialize the API
  service = Google::Apis::CalendarV3::CalendarService.new
  service.client_options.application_name = APPLICATION_NAME
  service.authorization = authorize

  # Fetch the next 10 events for the user
  calendar_id = 'primary'
  response = service.list_events(calendar_id,
                                 max_results: 10,
                                 single_events: true,
                                 order_by: 'startTime',
                                 time_min: (Time.now).iso8601,
                                 time_max: (Time.now + 86400).iso8601,
                                 fields: 'items(end/date,start/date,summary)')
  response.items.find {|i|i.summary =~ /^WF/}&.summary
end


def post(message, opts={})
  webhook_url = '***REMOVED***'
  options = {
    channel: '#elements-humans',
    username: 'lindsay',
    icon_url: 'https://ca.slack-edge.com/***REMOVED***-U43EQGRQB-32d2749f6e4b-72'
  }.merge(opts)

  notifier = Slack::Notifier.new(webhook_url, options)
  notifier.ping(message)
end

ENV['TZ'] = 'Australia/Sydney'

def main
  scheduler = Rufus::Scheduler.new
  scheduler.cron '29 8 * * 1-5 Australia/Sydney' do
    begin
      post(whereami)
    rescue => e
      p e
    end
  end
  scheduler.join
end

main()

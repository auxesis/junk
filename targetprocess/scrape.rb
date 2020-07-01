$LOAD_PATH << File.join(File.dirname(__FILE__), "lib")
require "tp"
require "dotenv"

Dotenv.load

tp = TargetProcess.new(token: ENV["TP_TOKEN"])

mod_squad_user_stories = tp.user_stories(where: "Project.Id eq 6429", take: 1000)

mod_squad_user_stories.each do |us|
  category = tp.last_work_category_change(id: us["Id"])
  if category
    formatted = [category["EntityID"], (category["NewValue"] || category["OldValue"])]
  else
    formatted = [us["Id"], "nil"]
  end
  puts formatted.join(",")
end

exit

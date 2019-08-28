import os
import time
import re
import sqlite3
from slackclient import SlackClient
from biobot_db import BioBotDB
import requests


# instantiate Slack client
slack_client = SlackClient(os.environ.get('SLACK_BOT_TOKEN'))
biobot_id = None

# constants
RTM_READ_DELAY = 0.2
MENTION_REGEX1 = "^<@(|[WU].+?)>(.*)"
MENTION_REGEX2 = "<@(|[WU].+?)>(.*)"
command_list = [
    "add bio",
    "remove bio",
    "display bio"
]

biobot_db = BioBotDB()

def parse_bot_commands(slack_events):
    """
        Parses a list of events coming from the Slack RTM API to find bot commands.
        If a bot command is found, this function returns a tuple of command and channel.
        If its not found, then this function returns None, None.
    """
    for event in slack_events:
        if event["type"] == "message" and not "subtype" in event:
            user_id, message = parse_direct_mention(event["text"])
            user = event["user"]
            if user_id == biobot_id:
                return message, event["channel"], user
    return None, None, None

def parse_direct_mention(message_text):
    """
        Finds a direct mention (a mention that is at the beginning) in message text
        and returns the user ID which was mentioned. If there is no direct mention, returns None
    """
    matches = re.search(MENTION_REGEX1, message_text)
    if not matches:
        matches = re.search(MENTION_REGEX2, message_text)
    # the first group contains the username, the second group contains the remaining message
    return (matches.group(1), matches.group(2).strip()) if matches else (None, None)

def post_message(channel, text, attachment=None):
    slack_client.api_call(
        "chat.postMessage",
        channel=channel,
        text=text,
        attachments=attachment
    )

def get_bio_data_from_user(user):
    missing = True
    while missing:
        for event in slack_client.rtm_read():
            if event["type"] == "message" and not "subtype" in event:
                if event["user"] == user:
                    bio_param = event["text"]
                    missing = False
    return bio_param

def handle_command(command, channel, user):
    """
        Executes bot command if the command is known
    """
    # Default response is help text for the user
    default_response = "Not sure what you mean <@{}>. Try *help*".format(user)

    # Finds and executes the given command, filling in response
    response = None
    # This is where you start to implement more commands!
    attachment = None
    if command.startswith("help"):
        response = "Possible commands are:\n- " + "\n- ".join(command_list)
    elif command.startswith("display bio"):
        info = command.split(' ')
        slack_id, msg = parse_direct_mention(command)
        if slack_id is None:
            response = "Please enter a person to display their bio!"
        else:
            image_url, response = biobot_db.select_bio_db(slack_id)
            attachment = [{"title": "Picture", "image_url": image_url}]
    elif command.startswith("remove bio"):
        biobot_db.delete_bio_db(user)
        response = "Bio deleted!"
    elif command.startswith("add bio"):
        response = "Sure thing, <@{}>! Can you tell me your name?".format(user)
        post_message(
            channel,
            text=response
        )
        add_bio_name = get_bio_data_from_user(user)

        response = "What is your role at OANDA?"
        post_message(
            channel,
            text=response
        )
        add_bio_role = get_bio_data_from_user(user)

        response = "Can you give me a brief description about yourself " \
        "(where are you from,\n what are your hobbies, what would you like people to know about you, etc)?"
        post_message(
            channel,
            text=response
        )
        add_bio_desc = get_bio_data_from_user(user)

        response = "Can you upload a picture of yourself?"
        post_message(
            channel,
            text=response
        )

        missing = True
        while missing:
            for event in slack_client.rtm_read():
                if event["type"] == "file_shared" and not "subtype" in event:
                    payload = {'token': os.environ.get('SLACK_BOT_TOKEN'), 'file' : event["file_id"]}
                    r = requests.get('https://slack.com/api/files.info', params=payload)
                    attributes = r.text.split(",")
                    for x in attributes:
                        if "\"user\"" in x:
                            p = x .split(':')
                            image_user = p[1].strip("\"")
                        if "\"url_private\"" in x:
                            j = x .split('\":')
                            imagee_url = j[1].strip("\"")
                    if image_user == user:
                        image_url = imagee_url.replace('\\', '')
                        missing = False

        response = "Thanks! Here's a rundown of what you added:\nName: {}\nRole: {}\nBiography: {}".format(add_bio_name, add_bio_role, add_bio_desc)
        slack_client.api_call(
            "chat.postMessage",
            channel=channel,
            text=response,
            attachments=[{"title": "Your Picture", "image_url": image_url}]
            )
        biobot_db.insert_bio_db(user, add_bio_name, add_bio_role, add_bio_desc, image_url)
        return

    # Sends the response back to the channel
    post_message(
        channel,
        text=response or default_response,
        attachment=attachment
    )

if __name__ == "__main__":

    if slack_client.rtm_connect(
        with_team_state=False,
        auto_reconnect=True
    ):
        print("BioBot connected and running!")
        # Read bot's user ID by calling Web API method `auth.test`
        biobot_id = slack_client.api_call("auth.test")["user_id"]
        while True:
            command, channel, user = parse_bot_commands(slack_client.rtm_read())
            if command:
                handle_command(command, channel, user)
            time.sleep(RTM_READ_DELAY)
    else:
        print("Connection failed. Exception traceback printed above.")
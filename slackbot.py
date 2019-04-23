import json
import logging
import subprocess
from datetime import datetime
from os import path
from time import sleep

from slackclient import SlackClient


class SlackBot:
    def __init__(self, token_file):
        """
        Args:
            token_file:str: path to the file containing api token

        Attributes:
            client:SlackClinet: client instance with the given api token to perfom api calls
            userIdDict:dict: contains {"id": "real_name"} of the users in a Slack Workspace
        """

        if not path.exists(token_file):
            logger.critical(token_file + " not found!")
            exit(1)

        with open(token_file, 'rb') as f:
            api_token = (f.read().decode("latin-1")).strip()
            if not api_token.startswith("xoxb-"):
                logger.critical("malformed api token: " + api_token)
                exit(1)

        logger.debug("init client with token: " + api_token)
        self.client = SlackClient(api_token)
        self.userIdDict = {}

    def sendMessage(self, msg, channel):
        """
        This method posts a message to a public channel, private channel, or direct message/IM channel.
        """
        logger.debug('send \"{}\" to \"{}\"'.format(msg, channel))
        return self.client.api_call(
            "chat.postMessage",
            channel=channel,
            text=msg,
            as_user=True
        )

    def fetchHistory(self, channel):
        """
        This method returns a list of all messages from the specified conversation, latest to oldest.

        Args:
            channel:str: channel id

        Returns:
            msgs:list<str>: list of messages in the form of "date user: text"
        """
        hasMore = True
        cur_cursor = ""
        msgs = []
        sleep(0.5)  # dont spam the server if to much history is fechted
        while hasMore:
            logger.debug("fetch conversation history from " + channel)
            rsp = self.client.api_call(
                "conversations.history",
                channel=channel,
                cursor=cur_cursor
            )
            if rsp["ok"]:
                logging.debug("has more: " + str(rsp["has_more"]))
                hasMore = rsp["has_more"]
                for msg in rsp["messages"]:
                    user = self.userIdDict[msg["user"]]  # user real_name
                    text = msg["text"]
                    ts = int(msg["ts"].split('.')[0])  # unix timestamp
                    date = datetime.utcfromtimestamp(
                        ts).strftime('%Y-%m-%d %H:%M:%S')
                    msgs.append("{} {}: {}".format(date, user, text))
                logger.debug("added {} messages to history from {}".format(
                    len(msgs), channel))

                if hasMore:
                    # get next cursor
                    cur_cursor = rsp["response_metadata"]["next_cursor"]
            else:
                hasMore = False
                logger.error(json.dumps(rsp, indent=2))
        return msgs

    def initUserIdDict(self):
        """
        inits the self.userIdDict containing {"id: real_name"} for the workspace
        """
        logging.debug("try to fetch user list...")
        rsp = self.client.api_call("users.list")
        logging.debug(json.dumps(rsp, indent=2))
        if rsp["ok"]:
            for m in rsp["members"]:
                self.userIdDict[m["id"]] = m["real_name"]
            logging.debug("got {} users.".format(len(self.userIdDict)))
        else:
            logging.error("failed to fetch user list!")

    def enter_rtm_loop(self):
        """
        Starts the real time messaging loop
        """
        try:
            if self.client.rtm_connect(with_team_state=False):
                logger.info("Connected to rtm api...")
                online = True
                while online:
                    event = self.client.rtm_read()
                    self._parse_rtm_event(event)
                    sleep(1)
            else:
                logger.error("Connection Failed")
        except TimeoutError:
            logger.error("Connection timeout!")

    def _parse_rtm_event(self, event):
        """
        Try to parse an JSON respons and handle it.
        List of possible events and respons format under https://api.slack.com/rtm

        Args:
            event:json: JSON respons from the rtm websocket
        """
        if len(event) == 0:
            return  # got nothing, pass on

        rsp = event[0]  # rtm event comes as an list with one or none element
        try:
            if rsp["type"] == "message":  # got a message
                if "subtype" in rsp:  # has a subtype
                    if rsp["subtype"] == "message_deleted":  # message deleted
                        msg = rsp["previous_message"]["text"]
                        logger.info("\"{}\" got deleted!".format(msg))
                    elif rsp["subtype"] == "message_changed":  # message changed
                        old = rsp["previous_message"]["text"]
                        new = rsp["message"]["text"]
                        logger.info(
                            "\"{}\" got changed to \"{}\"".format(old, new))
                    else:
                        # unexpected rsp
                        logger.warning(json.dumps(event, indent=2))
                else:  # regular message
                    msg = rsp["text"]
                    userId = rsp["user"]
                    logger.info("msg: \"{}\" from \"{}\"".format(
                        msg, self.userIdDict[userId]))
                    if msg.startswith("."):  # msg is a command
                        self._parse_command(msg, userId)

            elif rsp["type"] == "hello":  # server hello
                logger.debug("got hello from server")
            elif rsp["type"] == "user_typing":  # user typing
                logger.info("{} is typing".format(
                    self.userIdDict[rsp["user"]]))
            elif rsp["type"] == "desktop_notification":  # notification
                logger.info("desktop_notification")
            else:
                logger.warning(json.dumps(event, indent=2))  # unexpected rsp
        except KeyError as ke:
            logger.error("KeyError: " + str(ke))
            logger.error(json.dumps(event, indent=2))

    def _parse_command(self, cmd, userId):
        """
        Args:
            cmd:str: command string to be parsed (the whole msg)
            userId:str: id of the user who wrote the command
        """
        commands = {"help": "displays this list of commands",
                    "fortune": "print a random, hopefully interesting, adage",
                    "echo": "test command"}

        # compose help text
        help_text = "List of available commands:\n"
        help_text += "```\n"
        for key in commands.keys():
            help_text += "{} - {}\n".format(key, commands[key])
        help_text += "```"

        # cut the leading dot and split
        cmd_split = (cmd.strip()[1:]).split()
        if len(cmd_split) == 0:
            return

        if not cmd_split[0] in commands.keys():
            self.sendMessage(
                "unknown command: *{}*".format(cmd_split[0]), userId)
            self.sendMessage(help_text, userId)
        elif cmd_split[0] == "help":
            self.sendMessage(help_text, userId)
        elif cmd_split[0] == "echo":
            del cmd_split[0]
            self.sendMessage(str(cmd_split), userId)
        elif cmd_split[0] == "fortune":
            proc = subprocess.Popen("fortune",
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
            out, err = proc.communicate(timeout=5)
            self.sendMessage(out, userId)


def main(token_file):
    logger.info("SlackBot started")
    sb = SlackBot(token_file)
    sb.initUserIdDict()
    sb.enter_rtm_loop()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(__file__)
    parser.add_argument("--token",
                        help="file containing the Slack API Token",
                        required=True)
    parser.add_argument("--log_level",
                        help="logging level",
                        choices=["DEBUG", "INFO",
                                 "WARNING", "ERROR", "CRITICAL"],
                        default="WARNING")
    parser.add_argument("--log_file",
                        help="file were the log gets written to e.g. \"slackbot.log\"",
                        default=None)
    args = parser.parse_args()

    numeric_level = getattr(logging, args.log_level.upper(), None)

    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=numeric_level,
        filename=args.log_file)

    if args.log_file:  # to also print everything that is logged if log_file is provided
        logging.getLogger().addHandler(logging.StreamHandler())

    logger = logging.getLogger("SlackBot")

    try:
        main(args.token)
    except KeyboardInterrupt:
        logger.info("stopped by user.")

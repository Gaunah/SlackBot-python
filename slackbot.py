import json
import logging
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

        logger.debug("token: " + api_token)
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

    def initUserIdDict(self):
        """
        inits the self.userIdDict containing {"id: real_name"} for the workspace
        """
        rsp = self.client.api_call("users.list")
        if rsp["ok"]:
            for m in rsp["members"]:
                self.userIdDict[m["id"]] = m["real_name"]

    def enter_rtm_loop(self):
        """
        Starts the real time messaging loop
        """
        if self.client.rtm_connect(with_team_state=False):
            logger.info("Connected to rtm api...")
            online = True
            while online:
                event = self.client.rtm_read()
                self._parse_rtm_event(event)
                sleep(1)
        else:
            logger.error("Connection Failed")

    def _parse_rtm_event(self, event):
        """
        Args:
            event:json: JSON respons from the rtm websocket
        """
        try:
            if len(event) > 0:
                rsp = event[0]
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
                            logger.warning(json.dumps(event, indent=2))
                    else:  # regular message
                        msg = rsp["text"]
                        userId = rsp["user"]
                        logger.info("msg: \"{}\" from \"{}\"".format(
                            msg, self.userIdDict[userId]))
                elif rsp["type"] == "hello":  # server hello
                    logger.debug("got hello from server")
                elif rsp["type"] == "user_typing":  # user typing
                    logger.info("{} is typing".format(
                        self.userIdDict[rsp["user"]]))
                elif rsp["type"] == "desktop_notification":  # notification
                    logger.info("desktop_notification")
                else:
                    logger.warning(json.dumps(event, indent=2))
        except KeyError as ke:
            logger.error("KeyError: " + str(ke))
            logger.error(json.dumps(event, indent=2))


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

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
            userIdDict:dict: contains {"real_name": "id"} of the users in a Slack Workspace
        """
        if not path.exists(token_file):
            print(token_file + " not found!")
            exit(1)

        with open(token_file, 'rb') as f:
            api_token = (f.read().decode("latin-1")).strip()

        print("token: " + api_token)
        self.client = SlackClient(api_token)
        self.userIdDict = {}

    def sendMessage(self, msg, channel):
        """
        This method posts a message to a public channel, private channel, or direct message/IM channel.
        """
        print('send \"{}\" to \"{}\"'.format(msg, channel))
        return self.client.api_call(
            "chat.postMessage",
            channel=channel,
            text=msg,
            as_user=True
        )

    def initUserIdDict(self):
        """
        inits the self.userIdDict containing {"real_name: id"} for the workspace
        """
        rsp = self.client.api_call("users.list")
        if rsp["ok"]:
            for m in rsp["members"]:
                self.userIdDict[m["real_name"]] = m["id"]

    def enter_rtm_loop(self):
        """
        Starts the real time messaging loop
        """
        if self.client.rtm_connect(with_team_state=False):
            print("Connected to rtm api...")
            online = True
            while online:
                event = self.client.rtm_read()
                self._parse_rtm_event(event)
                sleep(1)
        else:
            print("Connection Failed")

    def _parse_rtm_event(self, event):
        """
        Args:
            event:json: JSON respons from the rtm websocket
        """

        if len(event) > 0:
            rsp = event[0]
            if rsp["type"] == "message":
                # got a message
                msg = rsp["text"]
                print(msg)


def main():
    sb = SlackBot("slack_api_token")
    sb.initUserIdDict()
    sb.enter_rtm_loop()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("stopped by user.")

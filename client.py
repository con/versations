import os
import sys
from datetime import datetime

from colorama import Fore, Style
from nio import (
    AsyncClient,
    exceptions,
    LoginResponse,
    RoomMessageText,
    SyncResponse,
)

class VersationsClient(AsyncClient):
    def __init__(self, session, config=None, store_path=None):
        self.session = session
        super().__init__(
            homeserver=session.homeserver,
            user=session.user_id,
            store_path=store_path,
            config=config
        )
    async def write_message_event(self, room, event: RoomMessageText):
        """Callback to write a received message to disk.

        Arguments:
            room {MatrixRoom} -- Provided by nio
            event {RoomMessageText} -- Provided by nio
        """
        self._messages_written += 1
        event_dt = datetime.fromtimestamp(event.server_timestamp/ 1000)

        # Uncomment to see the messages in stdout for debugging
        # print(f"{event.sender}:{room.room_id}  {Fore.WHITE}{event_dt.strftime('%H:%M:%S')}: {Fore.MAGENTA}{event.body}{Style.RESET_ALL}")

        os.makedirs(os.path.join(self.store_path, room.display_name), exist_ok=True)
        with open(os.path.join(self.store_path, room.display_name, event_dt.date().isoformat()), "a") as log:
           log.write(f"{event_dt.strftime('%H:%M:%S')} | {event.sender}: {event.body}\n")

    @staticmethod
    def check_response(response, expected_type, fail_msg):
        if not isinstance(response, expected_type):
            raise Exception(fail_msg)

    async def log_messages(self):
        """Write each not-yet-synced message to log file"""
        self.add_event_callback(self.write_message_event, RoomMessageText)
        self._messages_written = 0

        print(f"{Fore.GREEN}Initial Sync{Style.RESET_ALL}")
        response = await self.sync(timeout=30000, full_state=True)
        self.check_response(response, SyncResponse, f"failed to sync  got {str(response)}")
        print(f"{Fore.GREEN}Retrieved {self._messages_written} messages")

        self.session.next_batch = response.next_batch

    async def password_login(self):
        if not self.session.password:
            print(f"{Fore.RED}Needed password, didnt have it. {Style.RESET_ALL}")
            sys.exit(1)

        resp = await self.login(password=self.session.password)
        self.check_response(resp, LoginResponse, fail_msg="Password login faild")
        print(f"{Fore.GREEN}Password login succeeded. Exporting the new access token to the environment.{Style.RESET_ALL}")

        self.session.device_id = resp.device_id
        self.session.access_token = resp.access_token
        # TODO
        # self.session.validate()
        self.session.write_to_disk()


    async def send_message(self, room_id, body=None):
        try:
            # We must ignore unverified, or we cannot send messages if anyone has an unverified device.
            await self.room_send(
                room_id=room_id,
                message_type="m.room.message",
                content={
                    "msgtype": "m.text",
                    "body": body,
                },
                ignore_unverified_devices=True,
            )
        except exceptions.OlmUnverifiedDeviceError:
            print("probably need to run the verify session")
            raise

    async def verify_session_with_emoji(self):
        print(f"""{Fore.GREEN}This device ({Fore.MAGENTA}{self.device_id}){Fore.GREEN} is ready and waiting
        for the other party to initiate an emoji verification with us by selecting
        "Verify by Emoji" in their Matrix client.{Style.RESET_ALL}""")
        print("...")
        print("...")
        print("...")
        await self.sync_forever(timeout=30000, full_state=True)


    # I just feel like this is bad
    def trust_user_all_devices(self, user_id):
        for device_id, olm_device in self.device_store[user_id].items():
            print(f"{Fore.YELLOW} Trusting {olm_device.display_name}/{device_id} from user {user_id} \\ Last Used ....TODO{Style.RESET_ALL}")
            self.verify_device(olm_device)


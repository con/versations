#
# import asyncio
# import getpass
# import json
import os
# import sys
# import traceback
# import rich
#
from nio import (
    AsyncClient,
#     AsyncClientConfig,
#     exceptions,
#     KeyVerificationCancel,
    KeyVerificationEvent,
#     KeyVerificationKey,
#     KeyVerificationMac,
#     KeyVerificationStart,
#     MatrixRoom,
#     MegolmEvent,
#     LocalProtocolError,
    LoginResponse,
#     RedactionEvent,
#     RedactedEvent,
#     RoomEncryptionEvent,
#     RoomGuestAccessEvent,
#     RoomMemberEvent,
    RoomMessageText,
#     RoomMessagesResponse,
#     RoomNameEvent,
#     SyncResponse,
#     ToDeviceError,
)
#
from datetime import datetime
# from session import Session
# from colorama import Fore, Style
#

# from client_callbacks import Callbacks
from colorama import Fore, Style

# file to store credentials in case you want to run program multiple times
class VersationsClient(AsyncClient):
    def __init__(self, session, config=None, store_path=None):
        self.session = session
        super().__init__(
            # TODO no store no path?
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
        # self._messages_written += 1
        event_dt = datetime.fromtimestamp(event.server_timestamp/ 1000)
        print(f"{event.sender}:{room.room_id}  {Fore.WHITE}{event_dt.strftime('%H:%M:%S')}: {Fore.MAGENTA}{event.body}{Style.RESET_ALL}")
            # if isinstance(event, MegolmEvent):
            #     if event.sender in self.device_store.users:
            #         # if event.device_id in self.device_store.users.mapping.get(event.device_id):
            #         print(f"{Fore.RED} {event.sender} {event.device_id}{Style.RESET_ALL}")
            #     print("skipping event that was sent by deleted device")
            # else:
            #     if isinstance(event, RedactionEvent):
            #     elif isinstance(event, RedactedEvent):
            #     elif isinstance(event, RoomMemberEvent):
            #     elif isinstance(event, RoomNameEvent):
            #     elif isinstance(event, RoomEncryptionEvent):
            #     elif isinstance(event, RoomGuestAccessEvent):
            #     else:
                    # raise
        os.makedirs(os.path.join(self.store_path, room.display_name), exist_ok=True)
        with open(os.path.join(self.store_path, room.display_name, event_dt.date().isoformat()), "a") as log:
           log.write(f"{event_dt.strftime('%H:%M:%S')} | {event.sender}: {event.body}\n")

    # look what golang has done to me
    @staticmethod
    def check_response(response, expected_type, fail_msg):
        if not isinstance(response, expected_type):
            raise Exception(fail_msg)



    async def password_login(self):
        if not self.session.password:
            print(f"{Fore.RED}Needed password, didnt have it. \n\n{Fore.GREEN}{HELP}{Style.RESET_ALL}")
            sys.exit(1)

        resp = await self.login(password=self.session.password)
        self.check_response(resp, LoginResponse, fail_msg="Password login faild")
        print(f"{Fore.GREEN}Password login succeeded. Exporting the new access token to the environment.{Style.RESET_ALL}")

        # TODO set all of them
        self.session.device_id = resp.device_id
        self.session.access_token = resp.access_token
        # self.session.validate()
        self.session.write_to_disk()


    async def say_hello(self, room_id):
        try:
            await self.room_send(
                room_id=room_id,
                message_type="m.room.message",
                content={
                    "msgtype": "m.text",
                    "body": "Hello, this message should be encrypted, let me know if theres a problem",
                },
            )
        except exceptions.OlmUnverifiedDeviceError as err:
            # TODO(all encrypted rooms?)
            print(f"probably need to run the verify session")
            raise
            # print(e)
    
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
            response = self.verify_device(olm_device)
    

import asyncio
import markdown
import os
import sys
from datetime import datetime

from colorama import Fore, Style
from nio import (
    AsyncClient,
    exceptions,
    LoginResponse,
    RoomMessageText,
    RoomSendResponse,
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
        # Registered once here rather than in log_messages(): add_event_callback
        # appends, so a second log_messages() call in the same run (send does
        # two) would leave two callbacks registered and log each event twice.
        self.add_event_callback(self.write_message_event, RoomMessageText)
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
        self._messages_written = 0

        print(f"{Fore.GREEN}Initial Sync{Style.RESET_ALL}")
        # matrix.org occasionally returns a malformed sync (e.g. missing
        # 'next_batch'), which nio surfaces as a SyncError. That's a transient
        # server blip, so retry with backoff before giving up and letting the
        # process exit non-zero (which the cron reports by email).
        backoffs = (30, 60, 120)
        for attempt in range(1, len(backoffs) + 2):  # 4 attempts total
            response = await self.sync(timeout=30000, full_state=True)
            if isinstance(response, SyncResponse):
                break
            # nio's SyncError is a dataclass (subclass of Response), not an
            # Exception, so sync() returns it rather than raising. Its __str__
            # already renders status_code + message, so just interpolate it.
            if attempt > len(backoffs):
                raise Exception(f"failed to sync after {attempt} attempts: {response}")
            wait = backoffs[attempt - 1]
            print(f"{Fore.YELLOW}sync attempt {attempt} failed ({response}); retrying in {wait}s{Style.RESET_ALL}")
            await asyncio.sleep(wait)
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


    async def send_message(self, room_id, body=None, convert_markdown=False):
        try:
            sections = body.split("##### ")  # Or another marker
            # The first section posts to the room timeline as usual; the rest
            # are threaded under it, so a long report is one timeline entry
            # with a "N replies" chip instead of N entries.
            thread_root = None
            for i, section in enumerate(sections):
                section_md = "##### " + section if i > 0 else section  # re-add heading
                if convert_markdown:
                    html = markdown.markdown(section_md)
                content = {
                    "msgtype": "m.text",
                    "format": "org.matrix.custom.html",
                    "body": section_md,
                    "formatted_body": html,
                }
                if thread_root is not None:
                    content["m.relates_to"] = {
                        "rel_type": "m.thread",
                        "event_id": thread_root,
                    }
                # We must ignore unverified, or we cannot send messages if anyone has an unverified device.
                response = await self.room_send(
                    room_id=room_id,
                    message_type="m.room.message",
                    content=content,
                    ignore_unverified_devices=True,
                )
                # room_send returns RoomSendError on failure, which has no
                # event_id. Without the root's id there is nothing to thread
                # under, so fail loudly rather than post the rest to the timeline.
                self.check_response(
                    response,
                    RoomSendResponse,
                    fail_msg=f"Failed to send section {i+1} of {len(sections)}: {response}",
                )
                if thread_root is None:
                    thread_root = response.event_id
                    print(f"{Fore.GREEN}Thread root: {thread_root}{Style.RESET_ALL}")
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


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


# Matrix caps a single event at 65536 bytes, and in an encrypted room the body
# is megolm-encrypted then base64-encoded (~4/3 expansion) before that limit is
# checked. A 16 KB markdown body renders to ~19 KB of HTML, so the event content
# is ~36 KB and ~48 KB on the wire once encrypted -- comfortably under the limit
# with room to grow. Sections larger than this are split across several messages
# rather than rejected with M_TOO_LARGE (which is what silently dropped the
# "Covered projects" section once its one line of repo links crept past ~48 KB).
MAX_BODY_BYTES = 16000


def split_to_budget(text, max_bytes=MAX_BODY_BYTES):
    """Break text into pieces each at most max_bytes UTF-8 bytes.

    Prefers to break on newlines, then on '; ' (the separator between repos in
    the one-line 'Covered projects' section), and falls back to a hard character
    split so even an unbreakable run still gets through.
    """
    if len(text.encode()) <= max_bytes:
        return [text]

    for sep in ("\n", "; "):
        if sep not in text:
            continue
        pieces, current = [], ""
        for part in text.split(sep):
            candidate = current + sep + part if current else part
            if len(candidate.encode()) <= max_bytes:
                current = candidate
            else:
                if current:
                    pieces.append(current)
                current = part
        if current:
            pieces.append(current)
        # A single part may still be over budget (e.g. one huge line); recurse
        # so it gets broken on the next-finer separator.
        result = []
        for piece in pieces:
            if len(piece.encode()) > max_bytes:
                result.extend(split_to_budget(piece, max_bytes))
            else:
                result.append(piece)
        return result

    # No separator helped: hard-split on character boundaries.
    result, current = [], ""
    for ch in text:
        if len((current + ch).encode()) > max_bytes:
            result.append(current)
            current = ch
        else:
            current += ch
    if current:
        result.append(current)
    return result


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
            # Re-add the heading that split() stripped, then break any section
            # that would overrun the Matrix event-size limit into several
            # messages. Whitespace-only chunks (e.g. an empty leading split)
            # are dropped so we never post a blank message.
            messages = []
            for i, section in enumerate(sections):
                section_md = "##### " + section if i > 0 else section
                for chunk in split_to_budget(section_md):
                    if chunk.strip():
                        messages.append(chunk)

            # The first message posts to the room timeline as usual; the rest
            # are threaded under it, so a long report is one timeline entry
            # with a "N replies" chip instead of N entries.
            thread_root = None
            for j, message_md in enumerate(messages):
                content = {
                    "msgtype": "m.text",
                    "body": message_md,
                }
                if convert_markdown:
                    content["format"] = "org.matrix.custom.html"
                    content["formatted_body"] = markdown.markdown(message_md)
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
                    fail_msg=f"Failed to send message {j+1} of {len(messages)}: {response}",
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


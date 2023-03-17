#!/usr/bin/env python3
import asyncio
import getpass
import json
import os
import sys
import traceback
import rich

from nio import (
    AsyncClient,
    AsyncClientConfig,
    exceptions,
    KeyVerificationCancel,
    KeyVerificationEvent,
    KeyVerificationKey,
    KeyVerificationMac,
    KeyVerificationStart,
    MatrixRoom,
    MegolmEvent,
    LocalProtocolError,
    LoginResponse,
    RedactionEvent,
    RedactedEvent,
    RoomEncryptionEvent,
    RoomGuestAccessEvent,
    RoomMemberEvent,
    RoomMessageText,
    RoomMessagesResponse,
    RoomNameEvent,
    # SqliteMemoryStore, broken
    store,
    SyncResponse,
    ToDeviceError,
)

from datetime import datetime
from session import Session
from colorama import Fore, Style

from client import VersationsClient
from client_callbacks import Callbacks


HELP = f"""
How to use this script:

Passwords, and all other variables to this program are set via environment variable:

#  - export MATRIX_KEYS_PASSPHRASE (Required) passphrase to decrypyt the session keys.
#  - export MATRIX_KEYS_PATH (Required) TODO would be nice if we did this automatically, but here we are.
#
#    -------YOU NEED TO DOWNLOAD THIS WITH YOUR CLIENT------
#    Using your client (exmple with Synapse):
#    - Settings > Export e2e room keys
#    - determine a passphrase
#    - download the keys, set this env var to match path
#
#  - export MATRIX_USERNAME (Required): this bot's matrix username
#  - export MATRIX_PASSWORD: (Required): Used to retrieve an access_token. Each time a
#               password is used, we create a new session and need to resync encryption.
#
#  - export MATRIX_DEVICE_ID: (Default: Random ala FMJXZUKEHU) Set this if you want to pick your device id. TODO would that even work?
#  - export MATRIX_ACCESS_TOKEN (Optional): Set this to override the access token from files. Typical use should not need to set this.
#  - export MATRIX_HOMESERVER: (Required) Should probably be https://matrix.org, but I don't want to default this one.
#
#  - export MATRIX_ROOM_ID (Optional): Needed for send and other things, but not sync.
#
#    export TODO (ACCESS TOKEN FILE SHOULD BE ENCRYPTED)
#  # export TODO(split into output and persistent)
#  - export MATRIX_STORE_PATH (Default: output/)
"""

async def main() -> None:
    session=Session.from_file()
    client_config = AsyncClientConfig(
        max_limit_exceeded=0,
        max_timeouts=0,
        store_sync_tokens=True,
        encryption_enabled=True,
    )
    client = VersationsClient(session=session, config=client_config, store_path="/mnt/datasets/con/matrix-archive")
    callbacks = Callbacks(client)
    client.add_to_device_callback(callbacks.to_device_callback, (KeyVerificationEvent,))
    if session.access_token:
        try:
            client.restore_login(user_id=session.user_id,
                                 device_id=session.device_id,
                                 access_token=session.access_token)
            print(f"{Fore.GREEN}Login restored from token{Style.RESET_ALL}")
            print(f"{Fore.WHITE} This device is: {Fore.MAGENTA}{session.device_id}{Style.RESET_ALL}")
        except LocalProtocolError as e:
            print(f"""{Fore.RED} There is an access token it still didnt wor. Maybe no device id?
            Thats a weird situation... probably you should just delete that
            session file and start from scratch.""")
    else: # First time
        print(f"{Fore.YELLOW}No access token, attempting password login.{Style.RESET_ALL}")
        # TODO configure
        # os.makedirs("output", exist_ok=True)
        # TODO unless response is error...
        # print("swallowing exception for token login: {e}")
        await client.password_login()
    # TODO this is bad. how can we do this better...
        # this doesnt need to be run every time. ?
        # add configuration?

    print("Loading encryption store.")
    print("(takes a minute)  ...")
    client.load_store()

    # TODO(if we are using exported keys, is this necessary?
    if session.new_session:
        print(f"""{Fore.GREEN}You've come so far, you're almost there.

            This next bit is annoying though. Before you can proceed,
                    {Fore.RED}youll need have access to second client logged into the same account
                    the account should be in a test room (dont do this in a public room and spam people)

            {Fore.WHITE}From your other client, Room options > people > your bot's account{Style.RESET_ALL}
           """)
        await client.verify_session_with_emoji()

    # Sync encryption keys with the server to participate in encrypted rooms
    if client.should_upload_keys:
        print("Updating keys")
        await client.keys_upload()


    if not (session.keys_path and session.keys_passphrase):
        raise Exception(HELP + "\n\n ...\nPlease set keys_path and passphrase")
    await client.import_keys(session.keys_path, session.keys_passphrase)

    # Trust the other bot devices
    client.trust_user_all_devices(session.user_id)
    # Trust foreach [users]
    # TODO store in session
    client.trust_user_all_devices("@asmacdo:matrix.org")

    # Write each message to file
    client.add_event_callback(client.write_message_event, RoomMessageText)
    client._messages_written = 0

    print(f"{Fore.GREEN}Initial Sync{Style.RESET_ALL}")
    response = await client.sync(timeout=30000, full_state=True)
    client.check_response(response, SyncResponse, f"failed to sync  got {str(response)}")

    session.next_batch = response.next_batch
    session.write_to_disk()

    await client.close()

try:
    asyncio.run(main())
except Exception:
    print(traceback.format_exc())
    sys.exit(1)
except KeyboardInterrupt:
    print("Received keyboard interrupt.")
    sys.exit(0)

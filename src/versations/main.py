#!/usr/bin/env python3
import asyncio
import os
import sys
import traceback
from functools import wraps

import click
from nio import (
    AsyncClientConfig,
    KeyVerificationEvent,
    LocalProtocolError,
)
from colorama import Fore, Style

from .client import VersationsClient
from .client_callbacks import Callbacks
from .session import Session


HELP = """
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
#    export TODO(split into output and persistent)
#  - export MATRIX_STORE_PATH (Default: output/)
"""

async def connect() -> VersationsClient:
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
        except LocalProtocolError:
            print(f"""{Fore.RED} There is an access token but it didnt work. Maybe no device id?
            Thats a weird situation... probably you should just delete that
            session file and start from scratch.""")
    else: # First time
        print(f"{Fore.YELLOW}No access token, attempting password login.{Style.RESET_ALL}")
        os.makedirs("output", exist_ok=True)
        await client.password_login()

    print("Loading encryption store. (takes a minute  ...)")
    client.load_store()

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

    if os.path.isfile(session.keys_path):
        await client.import_keys(session.keys_path, session.keys_passphrase)

    # Trust the other bot devices
    client.trust_user_all_devices(session.user_id)
    # TODO Trust foreach [users]
    client.trust_user_all_devices("@asmacdo:matrix.org")
    return client

def coro(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))
    return wrapper

@click.group(help="Versations is a Matrix bot that logs chat records and sends messages.")
def cli():
    pass

@cli.command(help="Sync with the specified room, and output to a file.")
@click.option("--room", help="Matrix Room ID to sync with")
@coro
async def sync(room):
    client = await connect()
    await client.log_messages()
    client.session.write_to_disk()
    await client.close()

@cli.command(help="Sync with a room and then send a message")
@click.option("--room", required=True, help="Matrix Room ID to send a message to.")
@click.option('-f', '--file', type=click.File('r'), help='Path to outgoing message file')
@click.option('--md', is_flag=True, default=False, help="Render the message as markdown.")
@click.argument("message", required=False)
@coro
async def send(room, file, md, message):
    if not (file or message):
        raise ValueError("Either the message string or a message file must be provided.")
    if file:
        message = file.read()
    client = await connect()
    await client.log_messages()
    await client.send_message(room, body=message, convert_markdown=md)
    # To capture the message we just sent. I dont feel strongly about keeping that.
    await client.log_messages()
    client.session.write_to_disk()
    await client.close()

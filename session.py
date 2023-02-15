import os
import yaml
from colorama import Fore, Style

DEFAULT_SESSION_PATH = "output/.session.yaml"

class Session:
    def __init__(self, user_id=None, new_session=True, access_token=None, device_id=None, homeserver=None, next_batch=None):
        self._new_session = new_session
        self.user_id = os.environ.get("MATRIX_USERNAME", user_id)
        self.password = os.environ.get("MATRIX_PASSWORD")
        self.homeserver = os.environ.get("MATRIX_HOMESERVER", homeserver)

        self.store_path = os.environ.get("MATRIX_STORE_PATH", "./output/")

        self.session_path = os.path.join(self.store_path, ".session.yaml")
        self.keys_path = os.path.join(self.store_path, ".keys")

        self.keys_passphrase = os.environ.get("MATRIX_KEYS_PASSPHRASE")
        self.access_token = access_token
        self._need_keys = True
        self.device_id = device_id
        self.next_batch = next_batch or ""
        self.new_session=new_session

    @classmethod
    # TODO(de-hardcod path
    def from_file(cls, path=DEFAULT_SESSION_PATH):
        try:
            with open(path, "r") as session_file:
                data = yaml.load(session_file.read(), Loader=yaml.Loader)
                data["new_session"] = False
                return cls(**data)
        except FileNotFoundError as e:
            print(f"{Fore.YELLOW}No session file found at at {path}{Style.RESET_ALL}")
            return cls(new_session=True)

    def write_to_disk(self):
        with open(self.session_path, "w") as token_file:
            store_vars = {
                "user_id": self.user_id,
                "device_id": self.device_id,
                "homeserver": self.homeserver,
                "access_token": self.access_token,
                # "room_id": self.room_id,
                # TODO we need another sync placeholder per room?
                "next_batch": self.next_batch,
            }
            token_file.write(yaml.dump(store_vars))

    # TODO use and make this good
    def validate(self):
        if self.access_token or self.password:
            return
        else:
            raise Exception("Need password or token. Got neither")


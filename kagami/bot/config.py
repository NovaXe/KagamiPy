import logging
import os
from dotenv import load_dotenv
from dataclasses import dataclass


@dataclass
class Configuration:
    token: str
    prefix: str
    owner_id: int
    data_path: str
    db_name: str
    lavalink: dict[str, str] = None
    spotify: dict[str, str] = None
    update_tables: bool = False
    drop_tables: bool = False
    drop_triggers: bool = False

    @classmethod
    def fromEnv(cls):
        load_dotenv()
        env = os.environ

        def get(var_name: str, type: type=str, default=None):
            val = env.get(var_name, None)
            if val is None:
                logging.warning(f"{var_name} missing in .env file")
                return default

            if type is bool:
                val = bool(int(val))
            elif type is int:
                val = int(val)
            elif type is float:
                val = float(val)
            elif type is str:
                pass
            else:
                raise RuntimeError(f"Invalid type '{type.__name__}'")

            return val

        conf = cls(
            token=get("BOT_TOKEN"),
            prefix=get("COMMAND_PREFIX", default="->"),
            owner_id=get("OWNER_ID", int),
            data_path=get("DATA_PATH"),
            db_name=get("DB_NAME"),
            lavalink={
                "uri": get("LAVALINK_URI"),
                "password": get("LAVALINK_PASSWORD")
            },
            spotify={
                "client_id": get("SPOTIFY_CLIENT_ID"),
                "client_secret": get("SPOTIFY_CLIENT_SECRET")
            },
            update_tables=get("UPDATE_TABLES", bool, False),
            drop_tables=get("DROP_TABLES", bool, False),
            drop_triggers=get("DROP_TRIGGERS", bool, False)
        )
        if not conf.token:
            raise RuntimeError("Missing token in environment")
        elif not conf.data_path:
            raise RuntimeError("Missing data path in environment")
        return conf


config = Configuration.fromEnv()

import logging
import json
import os
from dotenv import load_dotenv
from dataclasses import dataclass, field
from common.logging import setup_logging

logger = setup_logging(__name__)

# def envGet(var_name, type: type=str, default=None):
#     def get(var_name: str, type: type=str, default=None):
#             val = env.get(var_name, None)
#             if val is None:
#                 logging.warning(f"{var_name} missing in .env file")
#                 return default

#             if type is bool:
#                 val = bool(int(val))
#             elif type is int:
#                 val = int(val)
#             elif type is float:
#                 val = float(val)
#             elif type is str:
#                 pass
#             else:
#                 raise RuntimeError(f"Invalid type '{type.__name__}'")
#             return val
#     return field(default_factory = get(var_name, type, default))


@dataclass
class Configuration:
    token: str
    prefix: str
    owner_id: int
    log_level: str
    data_path: str
    db_name: str
    connection_pool_size: int
    lavalink: dict[str, str]=None
    spotify: dict[str, str]=None
    ignore_schema_updates: bool=False
    ignore_trigger_updates: bool=False
    drop_tables: bool=False
    drop_triggers: bool=False
    excluded_cogs: list=field(default_factory=list)

    @classmethod
    def fromEnv(cls):
        load_dotenv()
        env = os.environ

        def get(var_name: str, type: type=str, default=None):
            val = env.get(var_name, None)
            if val is None:
                logger.warning(f"{var_name} missing in .env file")
                return default

            if type is bool or type == "bool":
                val = bool(int(val))
            elif type is int or type == "int":
                val = int(val)
            elif type is float or type == "float":
                val = float(val)
            elif type is str or type == "str":
                pass
            elif type == "json":
                try: 
                    val = json.loads(val)
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid json for envirnment variable: {var_name}\n{e}")
                    raise e
            else:
                raise RuntimeError(f"Invalid type '{type.__name__}'")
            return val

        conf = cls(
            token=get("BOT_TOKEN"),
            prefix=get("COMMAND_PREFIX", default="->"),
            owner_id=get("OWNER_ID", int),
            log_level=l if (l:=get("LOG_LEVEL", str, "INFO")) in ["INFO", "DEBUG"] else "INFO",
            data_path=get("DATA_PATH"),
            db_name=get("DB_NAME"),
            connection_pool_size=get("CONNECTION_POOL_SIZE", int, 5),
            lavalink={
                "uri": get("LAVALINK_URI"),
                "password": get("LAVALINK_PASSWORD")
            },
            spotify={
                "client_id": get("SPOTIFY_CLIENT_ID"),
                "client_secret": get("SPOTIFY_CLIENT_SECRET")
            },
            ignore_schema_updates=get("IGNORE_SCHEMA_UPDATES", bool, False),
            ignore_trigger_updates=get("IGNORE_TRIGGER_UPDATES", bool, False), 
            drop_tables=get("DROP_TABLES", bool, False),
            drop_triggers=get("DROP_TRIGGERS", bool, False),
            excluded_cogs=get("EXCLUDED_COGS", "json", list())
        )
        if not conf.token:
            raise RuntimeError("Missing token in environment")
        elif not conf.data_path:
            raise RuntimeError("Missing data path in environment")
        return conf


config = Configuration.fromEnv()

import logging
import json
import os
from typing import TypeAlias, TypeVar, Any, Literal, cast
from dotenv import load_dotenv
from dataclasses import MISSING, dataclass, field
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


# T = TypeVar("T", bool, int, float, str, list[Any], dict[Any, Any], None)
# Primative: TypeAlias = bool | int | float | str
# ReturnType: TypeAlias = bool | int | float | str | list[Any] | dict[Any, Any]
# TypeLiteral = Literal["bool", "int", "float", "str", "json"]
# type FieldLiteral = Literal["bool", "int", "float", "str", "json"]
# type GenericFieldType = bool | int | float | str | list[Any] | dict[Any, Any]

@dataclass
class Configuration:
    token: str
    prefix: str
    owner_id: int
    log_level: str
    data_path: str
    db_name: str
    connection_pool_size: int
    lavalink: dict[str, str] | None=None
    spotify: dict[str, str] | None=None
    youtube: dict[str, str] | None=None
    ignore_schema_updates: bool=False
    ignore_trigger_updates: bool=False
    drop_tables: bool=False
    drop_triggers: bool=False
    excluded_cogs: list[str]=field(default_factory=list)

    @classmethod
    def fromEnv(cls):
        load_dotenv()
        env = os.environ

        def get[T: (bool, int, float, str, list[Any], dict[Any, Any])](var_name: str, field_type: type[T]=str, default: T | None=None) -> T:
            env_var: str | None = env.get(var_name, None)

            if env_var is None:
                if default is None:
                    message = f"{var_name} missing in .env file with missing default value"
                    logger.error(message)
                    raise RuntimeError(message)
                else:
                    logger.warning(f"{var_name} missing in .env file")
                    return default
            if field_type is bool:
                val = bool(int(env_var))
                # val = bool(int(env_var))
            elif field_type is int:
                val = int(env_var)
            elif field_type is float:
                val = float(env_var)
            elif field_type is str:
                val = env_var
            elif field_type is list or field_type is dict:
                assert isinstance(env_var, str)
                try: 
                    temp: list[Any] | dict[Any, Any] = json.loads(env_var)
                    val = cast(T, temp)
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid json for envirnment variable: {var_name}\n{e}")
                    raise e
            else:
                message = f"Invalid type specified '{type.__name__}' only `{repr(T)}` are accepted"
                logger.error(message)
                raise RuntimeError(message)
            # val = cast(T, val)
            assert isinstance(val, field_type), f"Return value of get expected: {repr(field_type)}, got: {repr(type(val))}"
            # assert isinstance(val, field_type)
            return val # Not sure how to make my generics work to get this val to not be an error in the typechecker

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
            youtube={
                "email": get("YOUTUBE_EMAIL"),
                "password": get("YOUTUBE_PASSWORD")
            },
            spotify={
                "client_id": get("SPOTIFY_CLIENT_ID"),
                "client_secret": get("SPOTIFY_CLIENT_SECRET")
            },
            ignore_schema_updates=get("IGNORE_SCHEMA_UPDATES", bool, False),
            ignore_trigger_updates=get("IGNORE_TRIGGER_UPDATES", bool, False), 
            drop_tables=get("DROP_TABLES", bool, False),
            drop_triggers=get("DROP_TRIGGERS", bool, False),
            excluded_cogs=get("EXCLUDED_COGS", list, list())
        )
        if not conf.token:
            raise RuntimeError("Missing token in environment")
        elif not conf.data_path:
            raise RuntimeError("Missing data path in environment")
        return conf


config = Configuration.fromEnv()

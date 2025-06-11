from typing import Any, cast
from dotenv import load_dotenv
import os
import json

from common.logging import setup_logging
logger = setup_logging(__name__)
env = os.environ

def get[T: (bool, int, float, str, list[Any], dict[Any, Any])](var_name: str, var_type: type[T]=str, default: T | None=None) -> T:
    """
    Type generic way of accessing a specific environment variable
    Still requires variables be hardcoded but accounts for them possibly being missing
    """
    load_dotenv()
    var: str | None = env.get(var_name, None)
    if var is None:
        if default is None:
            message = f"{var_name} missing in .env file with missing default value"
            logger.error(message)
            raise RuntimeError(message)
        else:
            logger.warning(f"{var_name} missing in .env file")
            return default
    if var_type is bool:
        val = bool(int(var))
        # val = bool(int(var))
    elif var_type is int:
        val = int(var)
    elif var_type is float:
        val = float(var)
    elif var_type is str:
        val = var
    elif var_type is list or var_type is dict:
        assert isinstance(var, str)
        try: 
            temp: list[Any] | dict[Any, Any] = json.loads(var)
            val = cast(T, temp)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid json for envirnment variable: {var_name}\n{e}")
            raise e
    else:
        message = f"Invalid type specified '{type.__name__}' only `{repr(T)}` are accepted"
        logger.error(message)
        raise RuntimeError(message)
    # val = cast(T, val)
    assert isinstance(val, var_type), f"Return value of get expected: {repr(var_type)}, got: {repr(type(val))}"
    # assert isinstance(val, var_type)
    return val # Not sure how to make my generics work to get this val to not be an error in the typechecker


token = get("BOT_TOKEN", str)
prefix = get("COMMAND_PREFIX", str, default="->")
owner_id = get("OWNER_ID", int)
admin_guild_id = get("ADMIN_GUILD_ID", int)
log_level=l if (l:=get("LOG_LEVEL", str, "INFO")) in ["INFO", "DEBUG"] else "INFO",

data_path = get("DATA_PATH", str)
db_name = get("DB_NAME", str)
connection_pool_size = get("CONNECTION_POOL_SIZE", int, 5)

lavalink_uri = get("LAVALINK_URI", str)
lavalink_password = get("LAVALINK_PASSWORD", str)

ignore_schema_updates = get("IGNORE_SCHEMA_UPDATES", bool, False)
ignore_trigger_updates = get("IGNORE_TRIGGER_UPDATES", bool, False)
ignore_index_updates = get("IGNORE_INDEX_UPDATES", bool, False)

drop_tables = get("DROP_TABLES", bool, False)
drop_triggers = get("DROP_TRIGGERS", bool, False)
drop_indexes = get("DROP_INDEXES", bool, False)
excluded_cogs = get("EXCLUDED_COGS", list, list()) # ['<cog_name>', '<cog_name>']


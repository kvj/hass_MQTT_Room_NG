from collections.abc import Mapping
from typing import Any, cast

from homeassistant import config_entries
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.selector import selector

from homeassistant.const import (
    CONF_NAME,
    CONF_DEVICE_ID,
)

from homeassistant.helpers.schema_config_entry_flow import (
    SchemaConfigFlowHandler,
    SchemaFlowFormStep,
    SchemaFlowError,
)

from .constants import (
    DOMAIN,
    CONF_SET_ICON,
    CONF_ROOM_AWAY_SECONDS,
    CONF_ROOM_AWAY_SECONDS_DEF,
    CONF_ROOM_CHANGE_SECONDS,
    CONF_HOME_AWAY_MODE,
    CONF_AREA_IDS,
)

import voluptuous as vol
import logging

_LOGGER = logging.getLogger(__name__)

OPTIONS_SCHEMA = vol.Schema({
    vol.Required(CONF_DEVICE_ID, description={}): selector({"text": {}}),
    vol.Required(CONF_SET_ICON, description={"suggested_value": False}): selector({"boolean": {}}),
    vol.Required(CONF_ROOM_AWAY_SECONDS, description={"suggested_value": str(CONF_ROOM_AWAY_SECONDS_DEF)}): selector({"text": {"type": "number"}}),
    vol.Optional(CONF_ROOM_CHANGE_SECONDS, description={}): selector({"text": {"type": "number"}}),
    vol.Optional(CONF_HOME_AWAY_MODE, description={"suggested_value": False}): selector({"boolean": {}}),
    vol.Optional(CONF_AREA_IDS, description={}): selector({"area": {"multiple": True}}),
})

CONFIG_SCHEMA = vol.Schema({
    vol.Required(CONF_NAME): selector({"text": {}}),
}).extend(OPTIONS_SCHEMA.schema)

async def _validate_options(step, user_input):
    _LOGGER.debug(f"_validate_options: {user_input}, {step}, {step.options}")
    return user_input

CONFIG_FLOW = {
    "user": SchemaFlowFormStep(CONFIG_SCHEMA, _validate_options),
}

OPTIONS_FLOW = {
    "init": SchemaFlowFormStep(OPTIONS_SCHEMA, _validate_options),
}

class ConfigFlowHandler(SchemaConfigFlowHandler, domain=DOMAIN):

    config_flow = CONFIG_FLOW
    options_flow = OPTIONS_FLOW

    def async_config_entry_title(self, options: Mapping[str, Any]) -> str:
        return cast(str, options[CONF_NAME])

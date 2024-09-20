from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)

from homeassistant.components.sensor import SensorEntity

import logging

from .constants import DOMAIN
from .coordinator import Coordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, add_entities):
    coordinator = entry.runtime_data
    add_entities([_Entity(coordinator)])
    return True


class _Entity(CoordinatorEntity, SensorEntity):

    def __init__(self, coordinator: Coordinator):
        super().__init__(coordinator)
        self._attr_has_entity_name = True
        self._attr_unique_id = f"mqtt_room_ng_{self.coordinator._entry_id}_"
        self._attr_name = self.coordinator.entity_name

    @property
    def native_value(self):
        return self.coordinator.entity_value

    @property
    def extra_state_attributes(self):
        return self.coordinator.entity_attributes

    @property
    def icon(self):
        return self.coordinator.entity_icon
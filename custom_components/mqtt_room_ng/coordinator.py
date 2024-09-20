from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    CoordinatorEntity,
)

from homeassistant.helpers import (
    area_registry,
    entity_registry,
)

from homeassistant.components import mqtt
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_NAME,
    STATE_UNKNOWN,
    STATE_HOME,
    STATE_NOT_HOME,
)


from .constants import (
    DOMAIN,
    CONF_ROOM_AWAY_SECONDS,
    CONF_ROOM_AWAY_SECONDS_DEF,
    CONF_ROOM_CHANGE_SECONDS,
    CONF_SET_ICON,
    CONF_HOME_AWAY_MODE,
    CONF_AREA_IDS,
)

import logging
import json
from datetime import timedelta, datetime

_LOGGER = logging.getLogger(__name__)

class Coordinator(DataUpdateCoordinator):

    def __init__(self, hass, entry):
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            setup_method=self._async_setup,
            update_method=self._async_update,
            update_interval=timedelta(seconds=10),
        )
        self._entry = entry
        self._entry_id = entry.entry_id
        self._mqtt_listener = None
        
    def _validate_device(self, device):
        _name = device.config.get("name")
        def _mid_point_ratio(r1: RoomConfig, r2: RoomConfig, ratio: float):
                tr1 = r1.tracker_absolute
                tr2 = r2.tracker_absolute
                return [tr1[0] + (tr2[0] - tr1[0]) * ratio, tr1[1] + (tr2[1] - tr1[1]) * ratio, tr1[2] + (tr2[2] - tr1[2]) * ratio]

        def _calculate_room(room1: str, room2: str) -> str:
            r1 = self._data.rooms.get(room1)
            r2 = self._data.rooms.get(room2)
            if r1 and r1.with_dimensions and r2 and r2.with_dimensions:
                r1_dist = device.rooms[room1].distance
                r2_dist = device.rooms[room2].distance
                ratio1 = r1_dist / (r1_dist + r2_dist)
                mid_point = _mid_point_ratio(r1, r2, ratio1)
                for k, room in self._data.rooms.items():
                    if room.with_dimensions and room.in_room(mid_point):
                        return k
            else:
                return None

        min_distance = None
        min_room = None
        ids = []
        for k, v in device.rooms.items():
            if v:
                delta = datetime.now() - v.last_update
                if delta > timedelta(milliseconds=device.config.get("interval", 1000)):
                    _LOGGER.debug(f"Expired device data [{_name}]: {k} {v} - {delta}")
                    v.expired = True
                    if delta > timedelta(seconds=60) or device.changed:
                        _LOGGER.debug(f"Invalidate device data - {device.changed}")
                        device.rooms[k] = None
                        continue
                ids.append(k)
        stats = {}
        for i in range(len(ids)-1):
            for j in range(i+1, len(ids)):
                room_id = _calculate_room(ids[i], ids[j])
                # _LOGGER.debug(f"_calc_room:[{_name}] {ids[i]} - {ids[j]} = {room_id}")
                if room_id:
                    stats[room_id] = stats.get(room_id, 0) + 1
        if len(stats):
            stats_sorted = sorted(stats.items(), key=lambda x: x[1], reverse=True)
            _LOGGER.debug(f"stats [{_name}] = {stats_sorted}")
            min_room = stats_sorted[0][0]
            min_distance = 0
        else:
            for k in ids:
                if min_distance is None or device.rooms[k].distance < min_distance:
                    min_room = k
                    min_distance = device.rooms[min_room].distance

        device.room = min_room     
        device.room_distance = min_distance
        device.changed = False

    def _all_coordinates_entries(self):
        entries = self.hass.config_entries.async_entries("coordinates", False, False)
        return filter(lambda x: x.runtime_data != None, entries)

    def _get_area_coordinates(self, area_id):
        entries = self._all_coordinates_entries()
        result = None
        for entry in entries:
            (entity, device, area) = entry.runtime_data.attachment
            coords = entry.runtime_data.entity_attributes["x_coordinates"]
            if area and area.id == area_id and len(coords) == 3:
                # Single point
                _LOGGER.debug(f"_async_get_area_coordinates: {entity} {device} {area} {coords}")
                return coords
        return None

    async def _async_update_location(self):
        # Calculate closest area, ignoring
        oldest = datetime.now() - timedelta(seconds=int(self._config.get(CONF_ROOM_AWAY_SECONDS, CONF_ROOM_AWAY_SECONDS_DEF)))
        area_id = None
        min_distance = None
        for (id, item) in self.data["areas"].items():
            if item["ts"] >= oldest:
                if min_distance is None or min_distance > item["distance"]:
                    min_distance = item["distance"]
                    area_id = id
        _LOGGER.debug(f"_async_update_location: {area_id} / {min_distance}, {self.data}")
        # Update next_area
        area = {"id": area_id, "distance": min_distance} if area_id else {"id": None, "distance": None}
        area["ts"] = datetime.now()
        if not self.data["area"]:
            # First time area defined
            self.data["area"] = area
        elif self.data["area"]["id"] == area_id:
            # Same area as before
            self.data["area"] = area
            self.data["next_area"] = None
        else:
            # The area is different
            if not self.data["next_area"]:
                self.data["next_area"] = area
            elif self.data["next_area"]["id"] != area_id:
                # Not the same as before
                self.data["next_area"] = area
            else:
                # Update distance
                self.data["next_area"]["distance"] = area["distance"]
            old = datetime.now() - timedelta(seconds=int(self._config.get(CONF_ROOM_CHANGE_SECONDS, 0)))
            if self.data["next_area"]["ts"] <= old:
                self.data["area"] = self.data["next_area"]
                self.data["next_area"] = None
        _LOGGER.debug(f"_async_update_location: Result: {self.data}")
        return {
            "area": self.data["area"],
            "next_area": self.data["next_area"],
        }
        

    async def _async_on_message(self, message):
        try:
            area_id = message.topic.split("/")[-1]
            payload = json.loads(message.payload)
            dist = payload.get("distance", 0.0)
            _LOGGER.debug(f"_async_on_message: {message}, {area_id} - {dist}")
            only_areas = self._config.get(CONF_AREA_IDS, [])
            if len(only_areas) and area_id not in only_areas:
                _LOGGER.debug(f"_async_on_message: Skip area {area_id} because of {only_areas}")
                return
            if area_id in self.data["areas"]:
                self.data["areas"][area_id]["ts"] = datetime.now()
            else:
                self.data["areas"][area_id] = {"ts": datetime.now()}
            self.data["areas"][area_id]["distance"] = dist
            self._set_data(await self._async_update_location())
        except:
            _LOGGER.exception(f"_async_on_message: {message}")

    async def _async_setup(self):
        self._config = self._entry.as_dict()["options"]
        self.data = {
            "areas": {},
            "area": None,
            "next_area": None,
        }

    async def _async_update(self):
        return {
            **self.data,
            **(await self._async_update_location()),
        }

    def _set_data(self, data):
        self.async_set_updated_data({
            **self.data,
            **data,
        })

    async def async_load(self):
        self._config = self._entry.as_dict()["options"]
        _LOGGER.debug(f"async_load: {self._config}")
        if not await mqtt.async_wait_for_mqtt_client(self.hass):
            _LOGGER.warn(f"async_load: No MQTT Client")
            return
        self._set_data({
            "areas": {},
            "area": None,
            "next_area": None,
        })
        self._mqtt_listener = await mqtt.async_subscribe(self.hass, "%s/+" % (self._config[CONF_DEVICE_ID]), self._async_on_message)

    async def async_unload(self):
        _LOGGER.debug(f"async_unload:")
        if self._mqtt_listener:
            self._mqtt_listener() # Unsubscribe
            self._mqtt_listener = None

    @property
    def area_entity(self):
        if area := self.data["area"]:
            if area_id := area["id"]:
                return area_registry.async_get(self.hass).async_get_area(area_id)
        return None

    @property
    def entity_name(self):
        return self._config[CONF_NAME]

    @property
    def entity_value(self):
        home_away = self._config.get(CONF_HOME_AWAY_MODE, False)
        if area := self.data["area"]:
            if area_id := area["id"]:
                return STATE_HOME if home_away else area_id
        return STATE_NOT_HOME if home_away else STATE_UNKNOWN

    @property
    def entity_attributes(self):
        data = {
            "distance": None,
            "area_id": None,
        }
        if area := self.data["area"]:
            data["distance"] = area.get("distance", None)
            data["area_id"] = area["id"]
            if coords := self._get_area_coordinates(area["id"]):
                data["x_coordinates"] = coords
                data["x_radius"] = data["distance"]
        return data

    @property
    def entity_icon(self):
        if self._config.get(CONF_SET_ICON, False):
            if area := self.area_entity:
                return area.icon
        return None
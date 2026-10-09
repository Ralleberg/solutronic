"""User-directed legacy-device removal must never delete current entities."""

import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from homeassistant.const import ATTR_RESTORED, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import frame

from custom_components.solutronic import async_remove_config_entry_device
from custom_components.solutronic.const import DOMAIN


class DeviceRemovalTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.hass = HomeAssistant(self.directory.name)
        if hasattr(frame, "async_setup"):
            frame.async_setup(self.hass)
        self.hass.config_entries = SimpleNamespace(
            async_get_entry=Mock(
                side_effect=lambda entry_id: self.entries.get(entry_id)
            ),
            async_reload=Mock(),
        )
        self.entry = SimpleNamespace(
            entry_id="current_entry",
            pref_disable_new_entities=False,
            domain=DOMAIN,
            title="Solutronic",
            disabled_by=None,
            subentries={},
        )
        self.entries = {self.entry.entry_id: self.entry}
        if hasattr(dr, "async_setup"):
            dr.async_setup(self.hass)
        await dr.async_load(self.hass)
        await er.async_load(self.hass)
        self.registry = er.async_get(self.hass)
        self.registry.async_schedule_save = Mock()
        self.devices = dr.async_get(self.hass)
        self.devices.async_schedule_save = Mock()
        self.legacy = self.devices.async_get_or_create(
            config_entry_id=self.entry.entry_id, identifiers={(DOMAIN, "192.0.2.1")}
        )
        self.current = self.devices.async_get_or_create(
            config_entry_id=self.entry.entry_id,
            identifiers={(DOMAIN, self.entry.entry_id)},
        )

    async def asyncTearDown(self):
        await self.hass.async_block_till_done()

    def add_entity(self, unique_id, device=None, entry=None, platform=DOMAIN, **kwargs):
        entry = entry or self.entry
        self.entries[entry.entry_id] = entry
        return self.registry.async_get_or_create(
            "sensor",
            platform,
            unique_id,
            config_entry=entry,
            device_id=(device or self.legacy).id,
            **kwargs,
        )

    async def can_remove(self, device=None):
        return await async_remove_config_entry_device(
            self.hass, self.entry, device or self.legacy
        )

    async def test_stale_ip_based_device_and_entities_can_be_removed_by_user(self):
        old = self.add_entity("192.0.2.1_PACL1")
        active = self.add_entity("current_entry_PACL1", device=self.current)
        before = dict(self.registry.entities)
        self.assertTrue(await self.can_remove())
        # The hook only permits HA's UI action; calling it never deletes anything.
        self.assertEqual(dict(self.registry.entities), before)
        self.assertIsNotNone(self.registry.async_get(old.entity_id))
        self.assertIsNotNone(self.registry.async_get(active.entity_id))
        self.hass.config_entries.async_reload.assert_not_called()

    async def test_current_device_is_protected_even_with_no_entities_or_coordinator(
        self,
    ):
        self.assertFalse(await self.can_remove(self.current))
        self.hass.data[DOMAIN] = {self.entry.entry_id: SimpleNamespace(data={})}
        self.assertFalse(await self.can_remove(self.current))

    async def test_ha_device_removal_cleans_old_entities_and_keeps_active_device(self):
        old = self.add_entity("192.0.2.1_PACL1")
        active = self.add_entity("current_entry_PACL1", device=self.current)
        self.assertTrue(await self.can_remove())
        # Simulate HA carrying out the approved device-page deletion.
        self.devices.async_remove_device(self.legacy.id)
        await self.hass.async_block_till_done()
        self.assertIsNone(self.devices.async_get(self.legacy.id))
        self.assertIsNone(self.registry.async_get(old.entity_id))
        self.assertIsNotNone(self.devices.async_get(self.current.id))
        self.assertEqual(
            self.registry.async_get(active.entity_id).unique_id, "current_entry_PACL1"
        )
        self.assertIs(self.entries[self.entry.entry_id], self.entry)
        self.hass.config_entries.async_reload.assert_not_called()

    async def test_current_unique_ids_protect_entities_attached_to_legacy_device(self):
        self.add_entity("current_entry_LIFETIME_DERIVED")
        self.assertFalse(await self.can_remove())

    async def test_disabled_current_entity_is_also_protected(self):
        self.add_entity(
            "current_entry_PACL2", disabled_by=er.RegistryEntryDisabler.USER
        )
        self.assertFalse(await self.can_remove())

    async def test_loaded_legacy_entity_is_protected_including_when_unavailable(self):
        entity = self.add_entity("192.0.2.1_PACL1")
        for value in ("1250", STATE_UNAVAILABLE):
            with self.subTest(value=value):
                self.hass.states.async_set(entity.entity_id, value)
                self.assertFalse(await self.can_remove())

    async def test_restored_placeholder_does_not_block_stale_device_removal(self):
        entity = self.add_entity("192.0.2.1_PACL1")
        self.hass.states.async_set(
            entity.entity_id, STATE_UNAVAILABLE, {ATTR_RESTORED: True}
        )
        self.assertTrue(await self.can_remove())

    async def test_entities_belonging_to_other_entries_or_integrations_are_protected(
        self,
    ):
        other_entry = SimpleNamespace(
            entry_id="another_entry", pref_disable_new_entities=False
        )
        entity = self.add_entity("other_PACL1", entry=other_entry)
        self.assertFalse(await self.can_remove())
        self.registry.async_remove(entity.entity_id)
        self.add_entity("unrelated_PACL1", platform="other_integration")
        self.assertFalse(await self.can_remove())

    async def test_empty_legacy_device_can_be_removed_but_unrelated_device_cannot(self):
        self.assertTrue(await self.can_remove())
        unrelated = SimpleNamespace(
            id="other_device", identifiers={("other_integration", "192.0.2.1")}
        )
        self.assertFalse(await self.can_remove(unrelated))

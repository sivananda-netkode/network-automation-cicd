
import pytest

from src.network.validators.vlan import (
    validate_vlan,
    validate_vlans,
)

from src.network.validators.dhcp import (
    validate_dhcp_pool,
    validate_dhcp_pools,
)


def test_validate_multiple_generated_vlans():
    """Validate many VLANs using the same reusable validator."""

    vlans = [
        {"id": vlan_id, "name": f"VLAN_{vlan_id}"}
        for vlan_id in range(10, 110)
    ]

    results = validate_vlans(vlans)

    assert len(results) == 100
    assert all(result["valid"] for result in results)


@pytest.mark.parametrize(
    "vlan, expected_valid",
    [
        ({"id": 10, "name": "ECE"}, True),
        ({"id": 0, "name": "INVALID"}, False),
        ({"id": 4095, "name": "INVALID"}, False),
        ({"id": 20, "name": ""}, False),
        ({"id": "invalid", "name": "TEST"}, False),
    ],
)
def test_vlan_validation_rules(vlan, expected_valid):
    result = validate_vlan(vlan)

    assert result["valid"] is expected_valid


def test_detect_duplicate_vlan_ids():
    vlans = [
        {"id": 10, "name": "ECE"},
        {"id": 10, "name": "CSE"},
    ]

    results = validate_vlans(vlans)

    assert results[0]["valid"] is True
    assert results[1]["valid"] is False
    assert "Duplicate VLAN ID" in results[1]["errors"]


def test_validate_multiple_generated_dhcp_pools():
    """Validate multiple DHCP pools using reusable logic."""

    pools = [
        {
            "name": f"POOL_{index}",
            "network": f"10.{index}.0.0 255.255.255.0",
            "default_routers": [f"10.{index}.0.1"],
            "dns_servers": ["8.8.8.8"],
            "other_commands": [],
        }
        for index in range(1, 101)
    ]

    results = validate_dhcp_pools(pools)

    assert len(results) == 100
    assert all(result["valid"] for result in results)


@pytest.mark.parametrize(
    "pool, expected_valid",
    [
        (
            {
                "name": "POOL",
                "network": "10.1.0.0 255.255.255.0",
                "default_routers": ["10.1.0.1"],
                "dns_servers": ["8.8.8.8"],
            },
            True,
        ),
        (
            {
                "name": "POOL",
                "network": "invalid-network",
                "default_routers": ["10.1.0.1"],
                "dns_servers": ["8.8.8.8"],
            },
            False,
        ),
        (
            {
                "name": "POOL",
                "network": "10.1.0.0 255.255.255.0",
                "default_routers": [],
                "dns_servers": ["8.8.8.8"],
            },
            False,
        ),
        (
            {
                "name": "POOL",
                "network": "10.1.0.0 255.255.255.0",
                "default_routers": ["10.2.0.1"],
                "dns_servers": ["8.8.8.8"],
            },
            False,
        ),
        (
            {
                "name": "POOL",
                "network": "10.1.0.0 255.255.255.0",
                "default_routers": ["10.1.0.1"],
                "dns_servers": ["invalid-dns"],
            },
            False,
        ),
    ],
)
def test_dhcp_validation_rules(pool, expected_valid):
    result = validate_dhcp_pool(pool)

    assert result["valid"] is expected_valid


def test_detect_duplicate_dhcp_pool_names():
    pools = [
        {
            "name": "USERS",
            "network": "10.1.0.0 255.255.255.0",
            "default_routers": ["10.1.0.1"],
            "dns_servers": ["8.8.8.8"],
        },
        {
            "name": "USERS",
            "network": "10.2.0.0 255.255.255.0",
            "default_routers": ["10.2.0.1"],
            "dns_servers": ["8.8.8.8"],
        },
    ]

    results = validate_dhcp_pools(pools)

    assert results[0]["valid"] is True
    assert results[1]["valid"] is False
    assert "Duplicate DHCP pool name" in results[1]["errors"]

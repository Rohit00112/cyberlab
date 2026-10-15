"""Tests for machine template spec validation and builder logic."""

from app.models.machine_templates import MachineTemplate
from app.services.templates import validate_template_spec


def test_template_validation_valid():
    tpl = MachineTemplate(
        slug="linux-web-vuln",
        title="Linux Web Vulnerability Lab",
        os_type="linux",
        architecture="x86_64",
        base_image="cyberlab/web-vuln:latest",
        exposure_policy="vpn_only",
        resource_spec={"cpu": 1.0, "memory_mb": 512},
    )
    res = validate_template_spec(tpl)
    assert res.is_valid is True
    assert len(res.errors) == 0


def test_template_validation_invalid_os():
    tpl = MachineTemplate(
        slug="invalid-os",
        title="Invalid OS Lab",
        os_type="solaris_sparc",
        architecture="x86_64",
        base_image="cyberlab/test:latest",
    )
    res = validate_template_spec(tpl)
    assert res.is_valid is False
    assert any("os_type" in err for err in res.errors)


def test_template_validation_missing_base_image():
    tpl = MachineTemplate(
        slug="no-image",
        title="No Image Lab",
        os_type="linux",
        architecture="x86_64",
        base_image="",
    )
    res = validate_template_spec(tpl)
    assert res.is_valid is False
    assert any("base_image" in err for err in res.errors)

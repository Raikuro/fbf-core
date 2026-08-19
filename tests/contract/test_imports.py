from fbf.core import domain, execution


def test_core_packages_importable() -> None:
    assert domain is not None
    assert execution is not None

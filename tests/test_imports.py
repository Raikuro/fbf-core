from engine import domain, application


def test_engine_packages_importable() -> None:
    assert domain is not None
    assert application is not None

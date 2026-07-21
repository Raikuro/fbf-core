def test_engine_package_importable() -> None:
    import engine  # noqa: WPS421

    assert engine is not None


def test_engine_application_importable() -> None:
    from engine import application  # noqa: WPS421

    assert application is not None


def test_engine_domain_importable() -> None:
    from engine import domain  # noqa: WPS421

    assert domain is not None

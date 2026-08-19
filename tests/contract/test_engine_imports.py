def test_core_package_importable() -> None:
    import fbf.core

    assert fbf.core is not None


def test_core_execution_importable() -> None:
    from fbf.core import execution

    assert execution is not None


def test_core_domain_importable() -> None:
    from fbf.core import domain

    assert domain is not None

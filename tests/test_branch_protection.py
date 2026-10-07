def test_branch_protection_blocks_failing_ci() -> None:
    assert False, "Intentional failure: verify that master branch protection blocks this PR"

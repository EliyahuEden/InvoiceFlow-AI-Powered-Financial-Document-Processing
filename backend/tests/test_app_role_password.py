"""Production: `migrate` sets the application role's password from APP_DB_PASSWORD, so the role created at first boot
never keeps the development password. The password is sent as a quoted literal, never pasted into the statement."""
from __future__ import annotations

import pytest

from app.cli import app_role_password_statement


def test_the_password_is_a_quoted_literal():
    stmt = app_role_password_statement("S3cret-'; DROP ROLE x; --")
    assert stmt.startswith('ALTER ROLE "invoiceflow_app" PASSWORD ')
    assert "'S3cret-''; DROP ROLE x; --'" in stmt           # the quote is doubled: it stays inside the literal


@pytest.mark.parametrize("weak", ["", "short", "invoiceflow_app_dev"])
def test_weak_or_development_passwords_are_refused(weak):
    with pytest.raises(ValueError):
        app_role_password_statement(weak)

"""Stored tokens have their own encryption key (TOKEN_ENCRYPTION_KEYS), separate from SECRET_KEY, with rotation.
Tokens encrypted before the key existed (derived from SECRET_KEY) must keep working until `tokens rotate` moves them."""
import pytest
from cryptography.fernet import Fernet, InvalidToken

from app import models as M
from app import security
from app.config import settings
from scripts import db as dbtool

from .conftest import make_client, signup_and_verify


@pytest.fixture
def keys(monkeypatch):
    """Set TOKEN_ENCRYPTION_KEYS for one test, and put the real keys back afterwards."""
    def use(*ks):
        monkeypatch.setattr(settings, "token_encryption_keys", list(ks))
        security.reload_token_keys()
    yield use
    monkeypatch.undo()
    security.reload_token_keys()


def _integration(db, secret: str) -> int:
    user = signup_and_verify(make_client(), email=f"t{Fernet.generate_key()[:6].hex()}@example.com")
    row = M.Integration(user_id=user["id"], provider="meta", secret=secret)
    db.add(row)
    db.commit()
    return row.id


def test_without_a_key_tokens_use_the_old_secret_key_derivation(keys):
    keys()
    token = security.encrypt_json({"access_token": "abc"})
    assert security.legacy_token_key().decrypt(token.encode())  # same as before this change: nothing breaks in dev
    assert security.token_key_status(token) == "current"


def test_new_key_encrypts_and_old_tokens_still_open(keys):
    keys()
    old = security.encrypt_json({"access_token": "old"})
    k1 = Fernet.generate_key().decode()
    keys(k1)
    new = security.encrypt_json({"access_token": "new"})
    assert Fernet(k1.encode()).decrypt(new.encode())
    with pytest.raises(InvalidToken):
        security.legacy_token_key().decrypt(new.encode())  # SECRET_KEY no longer opens new tokens
    assert security.decrypt_json(old) == {"access_token": "old"}
    assert security.token_key_status(old) == "old" and security.token_key_status(new) == "current"


def test_rotate_moves_everything_and_then_secret_key_can_change(db, keys, monkeypatch, capsys):
    keys()
    legacy_id = _integration(db, security.encrypt_json({"access_token": "from-before"}))
    k1, k2 = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    keys(k1)
    k1_id = _integration(db, security.encrypt_json({"access_token": "on-k1"}))
    keys(k2, k1)  # rotation: new key first, old one kept for decrypting
    db.add(M.ProviderConnection(user_id=db.get(M.Integration, k1_id).user_id, kind="text", adapter="openai", name="x",
                                secret=security.encrypt_json({"api_key": "sk-1"})))
    db.commit()

    assert dbtool.main(["tokens", "check"]) == 0
    assert "2 on an older key" in capsys.readouterr().out
    assert dbtool.main(["tokens", "rotate"]) == 0
    db.expire_all()
    assert all(security.token_key_status(r.secret) == "current" for r in db.scalars(dbtool.select(M.Integration)))

    keys(k2)  # old key dropped, SECRET_KEY changed: every token still opens
    monkeypatch.setattr(settings, "secret_key", "a-completely-different-secret-key-0123456789")
    security.reload_token_keys()
    assert security.decrypt_json(db.get(M.Integration, legacy_id).secret) == {"access_token": "from-before"}
    assert security.decrypt_json(db.get(M.Integration, k1_id).secret) == {"access_token": "on-k1"}
    assert dbtool.main(["tokens", "rotate"]) == 0
    assert "re-encrypted 0" in capsys.readouterr().out


def test_lost_key_is_reported_not_overwritten(db, keys, capsys):
    lost = Fernet.generate_key().decode()
    keys(lost)
    rid = _integration(db, security.encrypt_json({"access_token": "x"}))
    keys(Fernet.generate_key().decode())
    assert dbtool.main(["tokens", "check"]) == 1
    assert dbtool.main(["tokens", "rotate"]) == 1
    assert f"integrations#{rid}" in capsys.readouterr().out
    db.expire_all()
    assert Fernet(lost.encode()).decrypt(db.get(M.Integration, rid).secret.encode())  # left untouched


def test_bad_key_fails_loudly(keys):
    with pytest.raises(RuntimeError, match="TOKEN_ENCRYPTION_KEYS"):
        keys("not-a-fernet-key")


def test_new_key_prints_a_usable_key(capsys):
    assert dbtool.main(["tokens", "new-key"]) == 0
    Fernet(capsys.readouterr().out.strip().encode())

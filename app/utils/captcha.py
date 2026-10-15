import hashlib
import hmac
import secrets
import time
import uuid

from flask import current_app, session

from app import db
from app.models import LoginCaptcha


SESSION_KEY = 'login_captcha_id'
CAPTCHA_TTL_SECONDS = 300


def _answer_digest(challenge_id, answer):
    secret_key = current_app.config['SECRET_KEY']
    if not secret_key:
        raise RuntimeError('SECRET_KEY must be configured to issue login CAPTCHA challenges')

    return hmac.new(
        str(secret_key).encode(),
        f'{challenge_id}:{answer}'.encode(),
        hashlib.sha256,
    ).hexdigest()


def create_login_captcha():
    now = int(time.time())
    LoginCaptcha.query.filter(LoginCaptcha.expires_at <= now).delete(synchronize_session=False)

    previous_id = session.pop(SESSION_KEY, None)
    if previous_id:
        previous = db.session.get(LoginCaptcha, previous_id)
        if previous:
            db.session.delete(previous)

    first_number = secrets.randbelow(40) + 10
    second_number = secrets.randbelow(40) + 10
    challenge_id = uuid.uuid4().hex
    answer = str(first_number + second_number)

    db.session.add(LoginCaptcha(
        id=challenge_id,
        answer_digest=_answer_digest(challenge_id, answer),
        expires_at=now + CAPTCHA_TTL_SECONDS,
    ))
    db.session.commit()
    session[SESSION_KEY] = challenge_id

    return f'What is {first_number} + {second_number}?'


def verify_login_captcha(answer):
    challenge_id = session.pop(SESSION_KEY, None)
    if not challenge_id:
        return False

    challenge = db.session.get(LoginCaptcha, challenge_id)
    if not challenge:
        return False

    is_valid = (
        challenge.expires_at > int(time.time())
        and isinstance(answer, str)
        and hmac.compare_digest(
            challenge.answer_digest,
            _answer_digest(challenge_id, answer.strip()),
        )
    )
    db.session.delete(challenge)
    db.session.commit()
    return is_valid

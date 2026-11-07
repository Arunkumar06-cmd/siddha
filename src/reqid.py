"""Request correlation id: one value per HTTP request, visible everywhere.

The id is minted (or accepted from the caller) by the middleware in server.py,
held in a contextvar, stamped on every log record, returned as X-Request-ID and
sent upstream to Gnani as X-API-Request-ID, so one user turn can be followed
across our logs and the provider's support records.

No dependencies on purpose: config.py imports this module at start-up."""
import contextvars
import logging
import re
import uuid

NO_REQUEST = '-'  # shown in log lines written outside any request (start-up, scripts)

_current: contextvars.ContextVar[str] = contextvars.ContextVar('siddha_request_id', default=NO_REQUEST)
# Client identity for the per-client Gnani credit budget. Set by the HTTP
# middleware; direct pipeline calls (tests, scripts) fall back to 'anon'.
_client: contextvars.ContextVar[str] = contextvars.ContextVar('siddha_client', default='anon')

# Only a conservative charset is accepted from callers: the value lands in log lines.
_VALID = re.compile(r'^[A-Za-z0-9._-]{8,64}$')


def new_id() -> str:
    return uuid.uuid4().hex


def accept_or_new(candidate: str | None) -> str:
    """Use the caller's X-Request-ID when it is well-formed, else mint a fresh one."""
    if candidate and _VALID.match(candidate):
        return candidate
    return new_id()


def set_current(request_id: str) -> None:
    _current.set(request_id)


def current() -> str:
    return _current.get()


def set_client(client: str) -> None:
    """Identify the caller for the per-client Gnani credit budget."""
    _client.set(client)


def client() -> str:
    return _client.get()


def upstream(stage: str) -> str:
    """Per-call id for a provider request: '<request id>-<stage>'.

    Distinct per call (STT and TTS of one turn must not share an id in case the
    provider treats it as an idempotency key) but still prefixed by the request id."""
    rid = _current.get()
    return f'{new_id() if rid == NO_REQUEST else rid}-{stage}'


_installed = False


def install_log_factory() -> None:
    """Stamp record.request_id on every log record, whatever handler formats it.

    A record factory (not a handler filter) so it also covers handlers added later
    by uvicorn or pytest. Safe to call more than once."""
    global _installed
    if _installed:
        return
    previous = logging.getLogRecordFactory()

    def factory(*args, **kwargs):
        record = previous(*args, **kwargs)
        record.request_id = _current.get()
        return record

    logging.setLogRecordFactory(factory)
    _installed = True

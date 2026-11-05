"""Per-run delivery callback; ordinary SDK callers remain independent."""
from contextvars import ContextVar

contact_observer = ContextVar('contact_observer', default=None)
contact_media = ContextVar('contact_media', default=None)
contact_call = ContextVar('contact_call', default=None)


def notify(event):
    observer = contact_observer.get()
    if observer:
        observer(event)

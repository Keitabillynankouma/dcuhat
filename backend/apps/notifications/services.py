from __future__ import annotations

from .models import Notification, NotificationPreference


def notifier(destinataire, type_notification: str, *, titre: str, corps: str = "", cible=None):
    """Cree une notification si l'agent ne l'a pas desactivee."""
    preference = NotificationPreference.objects.filter(
        user=destinataire, type=type_notification
    ).first()
    if preference is not None and not preference.in_app:
        return None
    return Notification.objects.create(
        recipient=destinataire,
        type=type_notification,
        title=titre[:200],
        body=corps,
        target_type=(cible.__class__.__name__.upper() if cible is not None else ""),
        target_id=(str(cible.id) if cible is not None else ""),
    )


def notifier_plusieurs(destinataires, type_notification, *, titre, corps="", cible=None):
    return [
        notifier(d, type_notification, titre=titre, corps=corps, cible=cible)
        for d in destinataires
    ]

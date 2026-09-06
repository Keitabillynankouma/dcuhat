from __future__ import annotations

from .middleware import requete_courante
from .models import ActivityLog


def adresse_ip(request) -> str | None:
    if request is None:
        return None
    entete = request.META.get("HTTP_X_FORWARDED_FOR")
    if entete:
        return entete.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def journaliser(
    action: str,
    *,
    acteur=None,
    cible=None,
    target_type: str = "",
    target_id: str = "",
    target_path: str = "",
    service=None,
    device=None,
    **metadata,
) -> ActivityLog:
    """Ecrit une entree de journal. Ne leve jamais : un echec de journalisation
    ne doit pas faire echouer l'action metier, mais il est trace en log."""
    request = requete_courante()
    if acteur is None and request is not None:
        utilisateur = getattr(request, "user", None)
        if utilisateur is not None and utilisateur.is_authenticated:
            acteur = utilisateur

    if cible is not None:
        target_type = target_type or cible.__class__.__name__.upper()
        target_id = target_id or str(getattr(cible, "id", ""))
        if not target_path:
            target_path = getattr(cible, "chemin_complet", None) or getattr(
                cible, "path", ""
            )
        service = service or getattr(cible, "service", None)

    try:
        return ActivityLog.objects.create(
            actor=acteur,
            actor_label=str(acteur) if acteur else "systeme",
            action=action,
            target_type=target_type,
            target_id=target_id,
            target_path=target_path or "",
            service=service,
            device=device,
            ip_address=adresse_ip(request),
            user_agent=(request.META.get("HTTP_USER_AGENT", "")[:400] if request else ""),
            metadata=metadata or {},
        )
    except Exception:  # pragma: no cover
        import logging

        logging.getLogger(__name__).exception("Echec de journalisation de %s", action)
        return None

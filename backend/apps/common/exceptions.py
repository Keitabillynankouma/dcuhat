"""Erreurs metier de la plateforme, avec un code stable pour le client."""

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler as drf_exception_handler


class ErreurMetier(APIException):
    code_metier = "ERREUR"
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Erreur."

    def __init__(self, detail=None, **contexte):
        super().__init__(detail or self.default_detail)
        self.contexte = contexte


class PermissionRefusee(ErreurMetier):
    code_metier = "PERMISSION_DENIED"
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Vous n'avez pas les droits necessaires sur cet element."


class QuotaDepasse(ErreurMetier):
    code_metier = "QUOTA_EXCEEDED"
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    default_detail = "Le quota de stockage du service est atteint."


class ConflitDeNom(ErreurMetier):
    code_metier = "NAME_CONFLICT"
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Un element portant ce nom existe deja dans ce dossier."


class ConflitDeVersion(ErreurMetier):
    code_metier = "VERSION_CONFLICT"
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Le fichier a ete modifie entre-temps."


class FichierVerrouille(ErreurMetier):
    code_metier = "FILE_LOCKED"
    status_code = status.HTTP_423_LOCKED
    default_detail = "Ce fichier est verrouille par un autre agent."


class FormatNonSupporte(ErreurMetier):
    code_metier = "UNSUPPORTED_FORMAT"
    default_detail = "Ce format de fichier n'est pas pris en charge."


class ChecksumInvalide(ErreurMetier):
    code_metier = "CHECKSUM_MISMATCH"
    default_detail = "Le fichier recu est corrompu, veuillez le renvoyer."


class LienExpire(ErreurMetier):
    code_metier = "SHARE_LINK_EXPIRED"
    status_code = status.HTTP_410_GONE
    default_detail = "Ce lien de partage a expire ou a ete revoque."


class OperationInvalide(ErreurMetier):
    code_metier = "INVALID_OPERATION"
    default_detail = "Operation impossible."


def dcuhat_exception_handler(exc, context):
    reponse = drf_exception_handler(exc, context)
    if reponse is None:
        return None
    code = getattr(exc, "code_metier", None)
    if code is None:
        code = {
            400: "VALIDATION_ERROR",
            401: "NOT_AUTHENTICATED",
            403: "PERMISSION_DENIED",
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
            429: "THROTTLED",
        }.get(reponse.status_code, "ERREUR")
    detail = reponse.data
    if isinstance(detail, dict) and "detail" in detail and len(detail) == 1:
        detail = detail["detail"]
    reponse.data = {"code": code, "detail": detail}
    contexte = getattr(exc, "contexte", None)
    if contexte:
        reponse.data["contexte"] = contexte
    return reponse

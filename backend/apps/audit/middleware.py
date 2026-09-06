"""Rend la requete courante accessible au journal sans la faire circuler
dans toutes les signatures de fonctions."""

import threading

_local = threading.local()


class RequestContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _local.request = request
        try:
            return self.get_response(request)
        finally:
            _local.request = None


def requete_courante():
    return getattr(_local, "request", None)

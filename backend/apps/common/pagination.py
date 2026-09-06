from rest_framework.pagination import CursorPagination as DRFCursorPagination


class CursorPagination(DRFCursorPagination):
    """Pagination par curseur.

    Choisie plutot que la pagination par offset : pendant une synchronisation
    ou un televersement, des elements sont inseres en continu et un offset
    ferait sauter ou dupliquer des lignes.
    """

    page_size = 50
    max_page_size = 200
    page_size_query_param = "taille"
    ordering = "-created_at"

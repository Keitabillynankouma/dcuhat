from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Notification, NotificationPreference
from .serializers import NotificationPreferenceSerializer, NotificationSerializer


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer

    def get_queryset(self):
        requete = Notification.objects.filter(recipient=self.request.user)
        if self.request.query_params.get("non_lues") == "1":
            requete = requete.filter(is_read=False)
        return requete

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        notification = self.get_object()
        notification.marquer_lue()
        return Response(NotificationSerializer(notification).data)

    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        nombre = self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({"marquees": nombre})

    @action(detail=False, methods=["get"])
    def compteur(self, request):
        return Response(
            {
                "non_lues": Notification.objects.filter(
                    recipient=request.user, is_read=False
                ).count()
            }
        )


class NotificationPreferenceViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationPreferenceSerializer

    def get_queryset(self):
        return NotificationPreference.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

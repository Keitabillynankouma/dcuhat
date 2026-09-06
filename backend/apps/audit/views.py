from __future__ import annotations

import csv

from django.http import HttpResponse
from rest_framework import serializers, viewsets
from rest_framework.decorators import action

from .models import ActivityLog


class ActivityLogSerializer(serializers.ModelSerializer):
    acteur_nom = serializers.CharField(source="actor_label", read_only=True)
    action_libelle = serializers.CharField(source="get_action_display", read_only=True)

    class Meta:
        model = ActivityLog
        fields = [
            "id", "actor", "acteur_nom", "action", "action_libelle", "target_type",
            "target_id", "target_path", "service", "ip_address", "metadata",
            "created_at",
        ]
        read_only_fields = fields


class ActivityLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Journal en lecture seule : aucune route de modification n'existe."""

    serializer_class = ActivityLogSerializer
    filterset_fields = ["action", "actor", "service", "target_type"]

    def get_queryset(self):
        requete = ActivityLog.objects.select_related("actor", "service")
        utilisateur = self.request.user
        if utilisateur.est_admin or utilisateur.est_directeur:
            pass
        elif utilisateur.est_chef_service and utilisateur.service_id:
            requete = requete.filter(service_id=utilisateur.service_id)
        else:
            requete = requete.filter(actor=utilisateur)
        params = self.request.query_params
        if params.get("date_from"):
            requete = requete.filter(created_at__gte=params["date_from"])
        if params.get("date_to"):
            requete = requete.filter(created_at__lte=params["date_to"])
        if params.get("q"):
            requete = requete.filter(target_path__icontains=params["q"])
        return requete

    @action(detail=False, methods=["get"])
    def export(self, request):
        reponse = HttpResponse(content_type="text/csv; charset=utf-8")
        reponse["Content-Disposition"] = 'attachment; filename="journal-dcuhat.csv"'
        reponse.write("﻿")
        redacteur = csv.writer(reponse, delimiter=";")
        redacteur.writerow(
            ["Date", "Agent", "Action", "Type", "Chemin", "Adresse IP", "Details"]
        )
        for entree in self.get_queryset()[:20000]:
            redacteur.writerow(
                [
                    entree.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    entree.actor_label,
                    entree.get_action_display(),
                    entree.target_type,
                    entree.target_path,
                    entree.ip_address or "",
                    entree.metadata,
                ]
            )
        return reponse

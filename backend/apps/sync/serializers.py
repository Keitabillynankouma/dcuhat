from rest_framework import serializers

from .models import SyncOperation


class SyncOperationSerializer(serializers.ModelSerializer):
    class Meta:
        model = SyncOperation
        fields = [
            "id", "op_type", "target_type", "target_id", "payload", "client_seq",
            "base_version", "client_timestamp", "status", "conflict_resolution",
            "applied_at", "error", "result",
        ]
        read_only_fields = ["status", "conflict_resolution", "applied_at", "error", "result"]


class LotOperationsSerializer(serializers.Serializer):
    device = serializers.UUIDField()
    operations = serializers.ListField(child=serializers.DictField(), allow_empty=True)

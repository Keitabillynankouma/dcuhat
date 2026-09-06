from django.contrib import admin

from .models import Comment, File, FileMetadata, FileVersion, Folder, Tag


@admin.register(Folder)
class FolderAdmin(admin.ModelAdmin):
    list_display = ["path", "service", "owner", "file_count", "is_deleted"]
    list_filter = ["service", "is_deleted", "is_service_root"]
    search_fields = ["name", "path"]


class FileVersionInline(admin.TabularInline):
    model = FileVersion
    extra = 0
    readonly_fields = ["version_number", "size_bytes", "checksum_sha256", "uploaded_by"]


@admin.register(File)
class FileAdmin(admin.ModelAdmin):
    list_display = ["name", "folder", "kind", "size_bytes", "owner", "is_deleted"]
    list_filter = ["kind", "service", "is_deleted"]
    search_fields = ["name", "description"]
    inlines = [FileVersionInline]


admin.site.register([Tag, FileMetadata, Comment])
admin.site.site_header = "Administration DCUHAT"
admin.site.site_title = "DCUHAT"
admin.site.index_title = "Plateforme documentaire et geospatiale"

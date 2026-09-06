from django.contrib import admin

from .models import Permission, ShareLink

admin.site.register([Permission, ShareLink])

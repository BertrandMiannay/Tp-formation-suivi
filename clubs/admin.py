from django.contrib import admin

from .models import Club


@admin.register(Club)
class ClubAdmin(admin.ModelAdmin):
    list_display  = ('name', 'created_at')
    search_fields = ('name',)

    def delete_queryset(self, request, queryset):
        for club in queryset:
            club.delete()

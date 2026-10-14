from django.contrib import admin

from .models import Club, Membership


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    autocomplete_fields = ['user']


@admin.register(Club)
class ClubAdmin(admin.ModelAdmin):
    list_display  = ('name', 'created_at')
    search_fields = ('name',)
    inlines       = [MembershipInline]

    def delete_queryset(self, request, queryset):
        for club in queryset:
            club.delete()


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display  = ('user', 'club', 'role')
    list_filter   = ('club', 'role')
    search_fields = ('user__username', 'user__email')

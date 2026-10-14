from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from clubs.models import Membership

from .models import CustomUser


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Invitation', {'fields': ('invite_token', 'invite_expires_at')}),
        ('Clubs', {'fields': ('last_club',)}),
    )
    inlines = [MembershipInline]

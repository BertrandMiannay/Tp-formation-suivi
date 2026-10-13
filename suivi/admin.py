from django.contrib import admin

from .models import Attendance, Comment, TrainingSession, WorkedSkill


class AttendanceInline(admin.TabularInline):
    model = Attendance
    extra = 0
    autocomplete_fields = ['member']


@admin.register(TrainingSession)
class TrainingSessionAdmin(admin.ModelAdmin):
    list_display      = ('date', 'title', 'club', 'season')
    list_filter       = ('club', 'season')
    filter_horizontal = ('formations', 'instructors')
    inlines           = [AttendanceInline]


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('session', 'member', 'status')
    list_filter  = ('status', 'session__season')


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('date', 'member', 'session', 'skill', 'staff_only', 'author')
    list_filter  = ('staff_only',)
    raw_id_fields = ('member', 'session', 'skill')


@admin.register(WorkedSkill)
class WorkedSkillAdmin(admin.ModelAdmin):
    list_display = ('session', 'member', 'skill', 'status', 'author')
    list_filter  = ('status', 'session__season')

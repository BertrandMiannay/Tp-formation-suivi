from django.contrib import admin

from .models import Season, Member, Cursus, CursusCategory, Skill, MemberSkill, SkillEvaluation, Formation, Enrollment


admin.site.register(Season)


class EnrollmentInline(admin.TabularInline):
    model = Enrollment
    extra = 0
    autocomplete_fields = ['member']


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display      = ('last_name', 'first_name', 'user', 'medical_certificate_date')
    search_fields     = ('first_name', 'last_name', 'user__email')
    list_filter       = ('enrollments__formation',)
    autocomplete_fields = ['user']


@admin.register(Formation)
class FormationAdmin(admin.ModelAdmin):
    list_display      = ('name', 'cursus', 'start_date', 'end_date', 'status')
    list_filter       = ('status', 'cursus')
    filter_horizontal = ('managers',)
    inlines           = [EnrollmentInline]


class SkillInline(admin.TabularInline):
    model = Skill
    extra = 0
    ordering = ['order']


class CursusCategoryInline(admin.TabularInline):
    model = CursusCategory
    extra = 0
    ordering = ['order']


@admin.register(Cursus)
class CursusAdmin(admin.ModelAdmin):
    list_display = ('name', 'date', 'status')
    list_filter  = ('status',)
    inlines      = [CursusCategoryInline]


@admin.register(CursusCategory)
class CursusCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'cursus', 'order')
    inlines      = [SkillInline]


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'order')


admin.site.register(MemberSkill)


@admin.register(SkillEvaluation)
class SkillEvaluationAdmin(admin.ModelAdmin):
    list_display = ('date', 'member', 'skill', 'status', 'author')
    list_filter  = ('status', 'author')

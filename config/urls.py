from django.contrib import admin
from django.db import connection
from django.http import HttpResponse
from django.urls import path, include
from formation.urls import formation_urlpatterns, student_urlpatterns
from userManagement.views import HomeView


def health(request):
    """Healthcheck Docker / monitoring : l'application répond et la base est joignable."""
    connection.ensure_connection()
    return HttpResponse('ok', content_type='text/plain')


urlpatterns = [
    path('health/', health, name='health'),
    path('', HomeView.as_view(), name='home'),
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('invitations/', include('invitations.urls', namespace='invitations')),
    path('gestion/', include('formation.urls')),
    path('formations/', include(formation_urlpatterns)),
    path('eleves/', include(student_urlpatterns)),
    path('suivi/', include('suivi.urls')),
    path('users/', include('userManagement.urls')),
]

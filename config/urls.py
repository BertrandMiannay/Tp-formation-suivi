from django.contrib import admin
from django.db import connection
from django.http import Http404, HttpResponse
from django.urls import include, path, re_path
from formation.urls import formation_urlpatterns, student_urlpatterns
from userManagement.views import HomeView


def health(request):
    """Healthcheck Docker / monitoring : l'application répond et la base est joignable."""
    connection.ensure_connection()
    return HttpResponse('ok', content_type='text/plain')


def not_found(request, *args, **kwargs):
    raise Http404


urlpatterns = [
    path('health/', health, name='health'),
    path('', HomeView.as_view(), name='home'),
    path('admin/', admin.site.urls),
    # Seules la connexion et la déconnexion d'allauth servent : comptes créés sur invitation, mots de
    # passe réinitialisés par lien généré (aucun email n'est envoyé), email du compte géré par l'application.
    re_path(r'^accounts/(?!login/|logout/|inactive/)', not_found),
    path('accounts/', include('allauth.urls')),
    path('gestion/', include('formation.urls')),
    path('formations/', include(formation_urlpatterns)),
    path('eleves/', include(student_urlpatterns)),
    path('suivi/', include('suivi.urls')),
    path('users/', include('userManagement.urls')),
]

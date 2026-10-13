from django.contrib import admin
from django.contrib.auth.views import redirect_to_login
from django.db import connection
from django.http import Http404, HttpResponse
from django.shortcuts import redirect
from django.urls import include, path, re_path
from formation.urls import formation_urlpatterns, student_urlpatterns
from userManagement.views import HomeView


def health(request):
    """Healthcheck Docker / monitoring : l'application répond et la base est joignable."""
    connection.ensure_connection()
    return HttpResponse('ok', content_type='text/plain')


def not_found(request, *args, **kwargs):
    raise Http404


def admin_login(request, extra_context=None):
    """Connexion à l'admin Django par la page allauth, qui limite les tentatives (la page de connexion
    de l'admin n'a aucune limite)."""
    if request.user.is_authenticated:
        return redirect('admin:index' if request.user.is_staff else 'home')
    return redirect_to_login(request.GET.get('next') or '/admin/', login_url='account_login')


admin.site.login = admin_login


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
    path('clubs/', include('clubs.urls')),
]

from django.contrib import admin
from django.urls import path, include
from formation.urls import student_urlpatterns
from userManagement.views import HomeView

urlpatterns = [
    path('', HomeView.as_view(), name='home'),
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('invitations/', include('invitations.urls', namespace='invitations')),
    path('gestion/', include('formation.urls')),
    path('eleves/', include(student_urlpatterns)),
    path('suivi/', include('suivi.urls')),
    path('users/', include('userManagement.urls')),
]

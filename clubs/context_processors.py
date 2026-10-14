def user_clubs(request):
    """Clubs du compte connecté, pour le sélecteur de club de la barre de navigation."""
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {}
    return {'user_clubs': list(user.clubs().order_by('name', 'pk'))}

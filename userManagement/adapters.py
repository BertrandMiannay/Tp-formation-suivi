from allauth.account.adapter import DefaultAccountAdapter


class InvitationOnlyAccountAdapter(DefaultAccountAdapter):
    """Pas d'inscription libre : les comptes sont créés par invitation (`userManagement`)."""

    def is_open_for_signup(self, request):
        return False

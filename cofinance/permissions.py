from rest_framework import permissions

class IsClient(permissions.BasePermission):
    """
    Permet l'accès uniquement aux utilisateurs ayant le rôle 'client'.
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == 'client'


class IsAgent(permissions.BasePermission):
    """
    Permet l'accès uniquement aux agents de terrain.
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == 'agent'


class IsAdmin(permissions.BasePermission):
    """
    Permet l'accès uniquement aux administrateurs.
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and (request.user.role == 'admin' or request.user.is_superuser)


class IsAgentOrAdmin(permissions.BasePermission):
    """
    Permet l'accès aux agents et aux administrateurs.
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and (
            request.user.role in ['agent', 'admin'] or request.user.is_superuser
        )

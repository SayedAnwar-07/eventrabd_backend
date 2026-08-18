from rest_framework.permissions import BasePermission


class IsAdminUserOnly(BasePermission):
    """
    Allow access only to authenticated, active Django staff users.

    is_staff is the single source of truth for admin access.
    """

    message = "Admin access only."

    def has_permission(self, request, view):
        user = request.user

        return bool(
            user
            and user.is_authenticated
            and user.is_active
            and user.is_staff
        )
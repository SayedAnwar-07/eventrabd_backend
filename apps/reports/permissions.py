from rest_framework.permissions import BasePermission


class IsCustomer(BasePermission):
    message = "Only customers can access this feature."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and getattr(
                request.user,
                "role",
                None,
            ) == "customer"
        )


class IsAdmin(BasePermission):
    message = "Only admins can access this feature."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and getattr(
                request.user,
                "role",
                None,
            ) == "admin"
        )
from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsSellerBrandOwnerOrReadOnly(BasePermission):
    """
    Public can read.
    Only authenticated seller who owns the service brand can write.
    """

    message = "You can edit only services that belong to your own brand."

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True

        user = request.user

        if not user or not user.is_authenticated:
            self.message = "Authentication is required to edit this service."
            return False

        if getattr(user, "role", None) != "seller":
            self.message = "Only seller accounts can edit services."
            return False

        return True

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True

        user = request.user

        is_owner = (
            user.is_authenticated
            and getattr(user, "role", None) == "seller"
            and obj.brand.seller_id == user.id
        )

        if not is_owner:
            self.message = "You can edit only services that belong to your own brand."

        return is_owner
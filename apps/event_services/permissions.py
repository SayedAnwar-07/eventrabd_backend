from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsSellerBrandOwnerOrReadOnly(BasePermission):
    """
    Public can read.
    Only authenticated seller who owns the brand can write.
    """

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True

        user = request.user
        if not user or not user.is_authenticated:
            return False

        if getattr(user, "role", None) != "seller":
            return False

        return True

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True

        user = request.user
        return (
            user.is_authenticated
            and getattr(user, "role", None) == "seller"
            and obj.brand.seller_id == user.id
        )
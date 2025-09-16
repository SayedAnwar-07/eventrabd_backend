from django.shortcuts import get_object_or_404
from apps.users.models import User

def get_user_by_slug_or_404(slug: str, role: str) -> User:
    """
    Lookup User by generated slug and role (customer/seller).
    """
    for user in User.objects.filter(user_type=role):
        if user.get_profile_slug() == slug:
            return user
    # Force 404 if not found
    raise get_object_or_404(User, id="__invalid__")

from django.core.cache import cache


PUBLIC_SERVICES_CACHE_VERSION_KEY = (
    "public_services:cache_version"
)


def invalidate_public_services_cache():

    # Initialize version at zero if missing.
    cache.add(
        PUBLIC_SERVICES_CACHE_VERSION_KEY,
        0,
        timeout=None,
    )

    try:
        # Every invalidation increases the version.
        cache.incr(
            PUBLIC_SERVICES_CACHE_VERSION_KEY
        )

    except ValueError:

        # Recover if the key disappeared unexpectedly.
        cache.add(
            PUBLIC_SERVICES_CACHE_VERSION_KEY,
            0,
            timeout=None,
        )

        cache.incr(
            PUBLIC_SERVICES_CACHE_VERSION_KEY
        )

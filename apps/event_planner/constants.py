DIVISION_DISTRICTS = {
    "dhaka": [
        "Dhaka", "Faridpur", "Gazipur", "Gopalganj", "Kishoreganj",
        "Madaripur", "Manikganj", "Munshiganj", "Narayanganj",
        "Narsingdi", "Rajbari", "Shariatpur", "Tangail",
    ],
    "chattogram": [
        "Bandarban", "Brahmanbaria", "Chandpur", "Chattogram", "Cumilla",
        "Cox's Bazar", "Feni", "Khagrachhari", "Lakshmipur", "Noakhali",
        "Rangamati",
    ],
    "khulna": [
        "Bagerhat", "Chuadanga", "Jashore", "Jhenaidah", "Khulna",
        "Kushtia", "Magura", "Meherpur", "Narail", "Satkhira",
    ],
    "rajshahi": [
        "Bogura", "Chapainawabganj", "Joypurhat", "Naogaon", "Natore",
        "Pabna", "Rajshahi", "Sirajganj",
    ],
    "rangpur": [
        "Dinajpur", "Gaibandha", "Kurigram", "Lalmonirhat", "Nilphamari",
        "Panchagarh", "Rangpur", "Thakurgaon",
    ],
    "barishal": [
        "Barguna", "Barishal", "Bhola", "Jhalokathi", "Patuakhali", "Pirojpur",
    ],
    "sylhet": ["Habiganj", "Moulvibazar", "Sunamganj", "Sylhet"],
    "mymensingh": ["Jamalpur", "Mymensingh", "Netrokona", "Sherpur"],
}

DIVISION_CHOICES = [(key, key.title()) for key in DIVISION_DISTRICTS]

# Flat choices list for the District field — keeps admin/DRF browsable API usable
DISTRICT_CHOICES = sorted(
    {
        (district, district)
        for districts in DIVISION_DISTRICTS.values()
        for district in districts
    }
)

# districts belonging to more than one division would break the "district -> division"
# reverse lookup used by validate(); there are none in this dataset, but this check
# keeps it that way if someone edits the map later.
def _assert_no_duplicate_districts():
    seen = {}
    for division, districts in DIVISION_DISTRICTS.items():
        for d in districts:
            if d in seen and seen[d] != division:
                raise ValueError(f"District {d!r} listed under both {seen[d]!r} and {division!r}")
            seen[d] = division

_assert_no_duplicate_districts()
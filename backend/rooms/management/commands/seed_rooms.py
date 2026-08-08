import requests
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from rooms.models import Room, RoomImage

User = get_user_model()

ROOMS = [
    {
        "title": "Sunlit Studio, Dhanmondi",
        "room_type": Room.RoomType.STUDIO,
        "price": 12000,
        "area": Room.Area.DHANMONDI,
        "address": "House 12, Road 5, Dhanmondi, Dhaka",
        "lat": 23.7461,
        "lng": 90.3742,
        "amenities": ["WiFi", "AC", "Attached Bath", "Furnished"],
        "gender_preference": Room.GenderPreference.ANY,
        "size_sqft": 450,
        "is_available": True,
        "tier": Room.Tier.PREMIUM,
        "is_featured": True,
        "description": "Modern studio apartment with natural light, fully furnished with high-speed WiFi.",
        "owner_name": "Rahim Hossain",
        "verified": True,
        "rating": 4.8,
        "total_reviews": 24,
        "image_url": "https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?w=600&q=80",
    },
    {
        "title": "Cozy Single, Mirpur",
        "room_type": Room.RoomType.SINGLE,
        "price": 7500,
        "area": Room.Area.MIRPUR,
        "address": "Block C, Section 6, Mirpur, Dhaka",
        "lat": 23.8223,
        "lng": 90.3654,
        "amenities": ["WiFi", "Furnished"],
        "gender_preference": Room.GenderPreference.MALE,
        "size_sqft": 200,
        "is_available": True,
        "tier": Room.Tier.FEATURED,
        "is_featured": True,
        "description": "Peaceful single room in a safe residential area near metro station.",
        "owner_name": "Kamal Ahmed",
        "verified": True,
        "rating": 4.5,
        "total_reviews": 18,
        "image_url": "https://images.unsplash.com/photo-1631049307264-da0ec9d70304?w=600&q=80",
    },
    {
        "title": "Shared Premium, Gulshan",
        "room_type": Room.RoomType.SHARED,
        "price": 9500,
        "area": Room.Area.GULSHAN,
        "address": "Road 11, Gulshan 2, Dhaka",
        "lat": 23.7808,
        "lng": 90.4152,
        "amenities": ["WiFi", "AC", "Gym", "Furnished"],
        "gender_preference": Room.GenderPreference.ANY,
        "size_sqft": 350,
        "is_available": True,
        "is_featured": False,
        "description": "Premium shared accommodation in Gulshan with gym access and rooftop.",
        "owner_name": "Nadia Islam",
        "verified": True,
        "rating": 4.7,
        "total_reviews": 31,
        "image_url": "https://images.unsplash.com/photo-1555041469-a586c61ea9bc?w=600&q=80",
    },
    {
        "title": "Budget Room, Mohammadpur",
        "room_type": Room.RoomType.SINGLE,
        "price": 5000,
        "area": Room.Area.MOHAMMADPUR,
        "address": "Nurjahan Road, Mohammadpur, Dhaka",
        "lat": 23.7623,
        "lng": 90.3588,
        "amenities": ["WiFi"],
        "gender_preference": Room.GenderPreference.FEMALE,
        "size_sqft": 180,
        "is_available": False,
        "is_featured": False,
        "description": "Affordable room in a quiet neighborhood, ideal for students.",
        "owner_name": "Sumaiya Begum",
        "verified": False,
        "rating": 4.2,
        "total_reviews": 12,
        "image_url": "https://images.unsplash.com/photo-1586023492125-27b2c045efd7?w=600&q=80",
    },
    {
        "title": "Luxury Flat, Banani",
        "room_type": Room.RoomType.STUDIO,
        "price": 22000,
        "area": Room.Area.BANANI,
        "address": "Road 27, Banani, Dhaka",
        "lat": 23.7937,
        "lng": 90.4066,
        "amenities": ["WiFi", "AC", "Attached Bath", "Furnished", "Gym", "Parking"],
        "gender_preference": Room.GenderPreference.ANY,
        "size_sqft": 600,
        "is_available": True,
        "tier": Room.Tier.FEATURED,
        "is_featured": True,
        "description": "Luxury studio in the heart of Banani with all modern amenities.",
        "owner_name": "Arif Khan",
        "verified": True,
        "rating": 4.9,
        "total_reviews": 45,
        "image_url": "https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?w=600&q=80",
    },
    {
        "title": "Student Room, Azimpur",
        "room_type": Room.RoomType.SHARED,
        "price": 4500,
        "area": Room.Area.AZIMPUR,
        "address": "Azimpur Road, Azimpur, Dhaka",
        "lat": 23.7226,
        "lng": 90.3874,
        "amenities": ["WiFi", "Furnished"],
        "gender_preference": Room.GenderPreference.MALE,
        "size_sqft": 160,
        "is_available": True,
        "is_featured": False,
        "description": "Affordable shared room near Dhaka University campus.",
        "owner_name": "Sabbir Rahman",
        "verified": False,
        "rating": 4.0,
        "total_reviews": 8,
        "image_url": "https://images.unsplash.com/photo-1493809842364-78817add7ffb?w=600&q=80",
    },
    {
        "title": "Modern Studio, Mirpur",
        "room_type": Room.RoomType.STUDIO,
        "price": 13500,
        "area": Room.Area.MIRPUR,
        "address": "Mirpur 10 Circle, Mirpur, Dhaka",
        "lat": 23.8180,
        "lng": 90.3690,
        "amenities": ["WiFi", "AC", "Furnished", "Attached Bath"],
        "gender_preference": Room.GenderPreference.ANY,
        "size_sqft": 420,
        "is_available": True,
        "is_featured": False,
        "description": "Bright modern studio close to Mirpur 10 metro station, ideal for young professionals.",
        "owner_name": "Farhana Akter",
        "verified": True,
        "rating": 4.6,
        "total_reviews": 15,
        "image_url": "https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?w=600&q=80",
    },
    {
        "title": "Executive Single, Banani",
        "room_type": Room.RoomType.SINGLE,
        "price": 15000,
        "area": Room.Area.BANANI,
        "address": "Banani DOHS, Banani, Dhaka",
        "lat": 23.7925,
        "lng": 90.4030,
        "amenities": ["WiFi", "AC", "Furnished", "Parking"],
        "gender_preference": Room.GenderPreference.MALE,
        "size_sqft": 250,
        "is_available": True,
        "is_featured": False,
        "description": "Well-furnished executive single room near Banani DOHS, walking distance to restaurants and cafes.",
        "owner_name": "Tanvir Islam",
        "verified": False,
        "rating": 4.4,
        "total_reviews": 20,
        "image_url": "https://images.unsplash.com/photo-1522771739844-6a9f6d5f14af?w=600&q=80",
    },
    {
        "title": "Fresh Studio, Uttara",
        "room_type": Room.RoomType.STUDIO,
        "price": 11000,
        "area": Room.Area.BANANI,
        "address": "House 4, Road 9, Uttara Sector 3, Dhaka",
        "lat": 23.8759,
        "lng": 90.3795,
        "amenities": ["WiFi", "AC", "Furnished"],
        "gender_preference": Room.GenderPreference.ANY,
        "size_sqft": 380,
        "is_available": True,
        "tier": Room.Tier.FREE,
        "is_featured": False,
        "description": "Brand new studio with a free tier — perfect for trying the Promote flow.",
        "owner_name": "Demo Promoter",
        "verified": True,
        "rating": 0,
        "total_reviews": 0,
        "image_url": "https://images.unsplash.com/photo-1493663284031-b7e3aefcae8e?w=600&q=80",
    },
    # ---- extra spread across Dhaka (map demo density, Phase 7) ----
    # These fill out the map view so clustering + travel-time overlay have
    # enough listings to show. All are metro-adjacent for the walk-time demo.
    {
        "title": "Compact Single, Motijheel",
        "room_type": Room.RoomType.SINGLE,
        "price": 6800,
        "area": Room.Area.AZIMPUR,
        "address": "Jubilee Road, Motijheel, Dhaka",
        "lat": 23.7331,
        "lng": 90.4181,
        "amenities": ["WiFi"],
        "gender_preference": Room.GenderPreference.MALE,
        "size_sqft": 180,
        "is_available": True,
        "is_featured": False,
        "description": "Budget single near Motijheel, minutes from the city's office district.",
        "owner_name": "Mahmudul Hasan",
        "verified": True,
        "rating": 4.1,
        "total_reviews": 9,
        "image_url": "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?w=600&q=80",
    },
    {
        "title": "Sunny Flat, Dhanmondi 27",
        "room_type": Room.RoomType.STUDIO,
        "price": 16000,
        "area": Room.Area.DHANMONDI,
        "address": "Road 27, Dhanmondi, Dhaka",
        "lat": 23.7434,
        "lng": 90.3773,
        "amenities": ["WiFi", "AC", "Furnished", "Attached Bath"],
        "gender_preference": Room.GenderPreference.ANY,
        "size_sqft": 480,
        "is_available": True,
        "tier": Room.Tier.FEATURED,
        "is_featured": True,
        "description": "Bright flat on Dhanmondi 27 with a balcony and fast fibre internet.",
        "owner_name": "Sharmin Sultana",
        "verified": True,
        "rating": 4.7,
        "total_reviews": 22,
        "image_url": "https://images.unsplash.com/photo-1493809842364-78817add7ffb?w=600&q=80",
    },
    {
        "title": "Cozy Studio, Mirpur 12",
        "room_type": Room.RoomType.STUDIO,
        "price": 9800,
        "area": Room.Area.MIRPUR,
        "address": "Section 12, Mirpur, Dhaka",
        "lat": 23.8230,
        "lng": 90.3661,
        "amenities": ["WiFi", "Furnished"],
        "gender_preference": Room.GenderPreference.FEMALE,
        "size_sqft": 300,
        "is_available": True,
        "is_featured": False,
        "description": "Quiet studio for women professionals, 10 minutes' walk from Mirpur 12.",
        "owner_name": "Tasnim Rahman",
        "verified": True,
        "rating": 4.4,
        "total_reviews": 11,
        "image_url": "https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?w=600&q=80",
    },
    {
        "title": "Gulshan 1 Shared Flat",
        "room_type": Room.RoomType.SHARED,
        "price": 10500,
        "area": Room.Area.GULSHAN,
        "address": "Gulshan 1, Dhaka",
        "lat": 23.7926,
        "lng": 90.4167,
        "amenities": ["WiFi", "AC", "Gym"],
        "gender_preference": Room.GenderPreference.ANY,
        "size_sqft": 380,
        "is_available": True,
        "is_featured": False,
        "description": "Shared flat in Gulshan 1 — walking distance to the metro and Gulshan Avenue.",
        "owner_name": "Farzana Chowdhury",
        "verified": False,
        "rating": 4.3,
        "total_reviews": 14,
        "image_url": "https://images.unsplash.com/photo-1555041469-a586c61ea9bc?w=600&q=80",
    },
    {
        "title": "Uttara Sector 7 Family Room",
        "room_type": Room.RoomType.SHARED,
        "price": 8200,
        "area": Room.Area.BANANI,
        "address": "Road 4, Uttara Sector 7, Dhaka",
        "lat": 23.8642,
        "lng": 90.3995,
        "amenities": ["WiFi", "Furnished"],
        "gender_preference": Room.GenderPreference.FEMALE,
        "size_sqft": 260,
        "is_available": True,
        "is_featured": False,
        "description": "Family-friendly shared room steps from Uttara Sector 7 metro station.",
        "owner_name": "Rina Akhter",
        "verified": True,
        "rating": 4.5,
        "total_reviews": 17,
        "image_url": "https://images.unsplash.com/photo-1586023492125-27b2c045efd7?w=600&q=80",
    },
    {
        "title": "Mohammadpur Family Flat",
        "room_type": Room.RoomType.STUDIO,
        "price": 12500,
        "area": Room.Area.MOHAMMADPUR,
        "address": "Shyamoli, Mohammadpur, Dhaka",
        "lat": 23.7706,
        "lng": 90.3619,
        "amenities": ["WiFi", "AC", "Parking", "Furnished"],
        "gender_preference": Room.GenderPreference.ANY,
        "size_sqft": 450,
        "is_available": True,
        "is_featured": False,
        "description": "Spacious family flat near Shyamoli with parking and a rooftop terrace.",
        "owner_name": "Jahir Uddin",
        "verified": False,
        "rating": 4.2,
        "total_reviews": 6,
        "image_url": "https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?w=600&q=80",
    },
]


class Command(BaseCommand):
    help = "Seed the database with 8 sample rooms matching the frontend mock data."

    def get_or_create_owner(self, full_name):
        username = full_name.lower().replace(" ", ".")
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "email": f"{username}@rentora.com",
                "first_name": full_name.split(" ")[0],
                "last_name": " ".join(full_name.split(" ")[1:]),
                "role": User.Role.LANDLORD,
                "nid_verified": True,
            },
        )
        if created:
            user.set_password("demo12345")
            user.save(update_fields=["password"])
            self.stdout.write(f"  created landlord user '{username}'")
        return user

    def attach_primary_image(self, room, image_url):
        try:
            response = requests.get(image_url, timeout=10)
            response.raise_for_status()
        except requests.RequestException as exc:
            self.stdout.write(
                self.style.WARNING(f"  could not download image for '{room.title}': {exc}")
            )
            return
        filename = f"{room.pk}-primary.jpg"
        RoomImage.objects.create(
            room=room,
            image=ContentFile(response.content, name=filename),
            is_primary=True,
        )

    def handle(self, *args, **options):
        for data in ROOMS:
            data = dict(data)
            owner_name = data.pop("owner_name")
            image_url = data.pop("image_url")

            if Room.objects.filter(title=data["title"]).exists():
                self.stdout.write(f"Skipping '{data['title']}' - already exists")
                continue

            owner = self.get_or_create_owner(owner_name)
            room = Room.objects.create(owner=owner, **data)
            self.attach_primary_image(room, image_url)
            self.stdout.write(self.style.SUCCESS(f"Created room '{room.title}'"))

        self.stdout.write(
            self.style.SUCCESS(f"Done. {Room.objects.count()} room(s) total in the database.")
        )

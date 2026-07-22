from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        TENANT = "tenant", "Tenant"
        LANDLORD = "landlord", "Landlord"
        ADMIN = "admin", "Admin"

    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        OTHER = "other", "Other"

    phone = models.CharField(max_length=20, blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.TENANT)
    gender = models.CharField(max_length=10, choices=Gender.choices, blank=True)
    nid_verified = models.BooleanField(default=False)
    bio = models.TextField(blank=True)
    date_of_birth = models.DateField(null=True, blank=True)

    def __str__(self):
        return self.username

from django.contrib import admin

from .models import CorporateAccount, CorporateInvoice, CorporateMember


@admin.register(CorporateAccount)
class CorporateAccountAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "status", "email", "created_at")
    list_filter = ("status",)
    search_fields = ("name", "email")


@admin.register(CorporateMember)
class CorporateMemberAdmin(admin.ModelAdmin):
    list_display = ("account", "user", "role")
    list_filter = ("role",)


@admin.register(CorporateInvoice)
class CorporateInvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "account", "amount", "status", "period_start", "period_end")
    list_filter = ("status",)

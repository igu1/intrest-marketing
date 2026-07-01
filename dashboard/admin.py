from django.contrib import admin
from .models import IdentifiedUser, BulkCampaign, MessageRecipient


@admin.register(IdentifiedUser)
class IdentifiedUserAdmin(admin.ModelAdmin):
    list_display = ("username", "chat_id", "first_seen", "last_seen")
    search_fields = ("username", "chat_id")


@admin.register(BulkCampaign)
class BulkCampaignAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "total_sent", "total_failed", "created_at")
    list_filter = ("status",)


@admin.register(MessageRecipient)
class MessageRecipientAdmin(admin.ModelAdmin):
    list_display = ("name", "chat_id", "campaign", "status")
    list_filter = ("status",)

from django.db import models


class IdentifiedUser(models.Model):
    chat_id = models.CharField(max_length=255, unique=True)
    username = models.CharField(max_length=255)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["username"]

    def __str__(self):
        return f"{self.username} ({self.chat_id})"


class BulkCampaign(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("sending", "Sending"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    name = models.CharField(max_length=255)
    message_text = models.TextField()
    image = models.ImageField(upload_to="campaigns/", blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    total_sent = models.PositiveIntegerField(default=0)
    total_failed = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class MessageRecipient(models.Model):
    campaign = models.ForeignKey(BulkCampaign, on_delete=models.CASCADE, related_name="recipients")
    name = models.CharField(max_length=255)
    chat_id = models.CharField(max_length=255)
    status = models.CharField(max_length=20, default="pending")
    error_message = models.TextField(blank=True)

    def __str__(self):
        return f"{self.name} ({self.chat_id})"

from django.conf import settings
from django.db import models

from learning.models import Material


class Recommendation(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recommendations")
    material = models.ForeignKey(Material, on_delete=models.CASCADE, related_name="recommendations")
    reason = models.TextField()
    score = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    source = models.CharField(max_length=50, default="rules")
    related_message_id = models.PositiveBigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-score", "-created_at"]

    def __str__(self) -> str:
        return f"{self.student} -> {self.material}"

# Create your models here.

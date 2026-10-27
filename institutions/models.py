import secrets

def join_token():
    return secrets.token_urlsafe(24)

from django.core.exceptions import ValidationError
from django.db import models

from .tenancy import InstitutionManager, current_institution_id, owned_institution_id, validate_institution_links


class Institution(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=60, unique=True, verbose_name='Institution code')
    email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)
    is_original = models.BooleanField(default=False, editable=False)
    join_code = models.CharField(max_length=64, unique=True, default=join_token, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Institutions'

    def __str__(self):
        return self.name


class InstitutionOwnedModel(models.Model):
    institution = models.ForeignKey(Institution, on_delete=models.PROTECT, default=owned_institution_id, editable=False)
    objects = InstitutionManager()
    all_institutions = models.Manager()

    class Meta:
        abstract = True

    def validate_institution(self):
        current = current_institution_id()
        if current and self.institution_id != current:
            raise ValidationError({'institution': 'This record belongs to another institution.'})
        if self.pk and not self._state.adding:
            stored = type(self)._base_manager.filter(pk=self.pk).values_list('institution_id', flat=True).first()
            if stored and stored != self.institution_id:
                raise ValidationError({'institution': 'Institution ownership cannot be changed.'})
        department = getattr(self, 'department', None)
        if department and department.institution_id != self.institution_id:
            raise ValidationError({'department': 'Choose a department in this institution.'})
        course_id = getattr(self, 'course_id', None)
        topic = getattr(self, 'topic', None)
        if course_id and topic and topic.course_id != course_id:
            raise ValidationError({'topic': 'Choose a topic in this module.'})
        validate_institution_links(type(self), self.institution_id, {
            field.attname: getattr(self, field.attname) for field in self._meta.concrete_fields if field.is_relation
        })

    def save(self, *args, **kwargs):
        self.validate_institution()
        return super().save(*args, **kwargs)


class Department(InstitutionOwnedModel):
    name = models.CharField(max_length=180)
    code = models.SlugField(max_length=40)
    class Meta:
        ordering = ['name']
        constraints = [models.UniqueConstraint(fields=['institution', 'code'], name='department_code_per_institution')]
    def __str__(self):
        return self.name

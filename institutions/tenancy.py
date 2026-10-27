"""Institution boundaries shared by requests, ORM queries, jobs and model writes."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models


_institution_id = ContextVar('institution_id', default=None)
_actor = ContextVar('institution_actor', default=None)


def current_institution_id():
    return _institution_id.get()


def default_institution_id():
    # Reserved by the initial data migration; model construction must not query
    # the database (Django also instantiates User during pre-migration checks).
    return 1


def owned_institution_id():
    return current_institution_id() or default_institution_id()


@contextmanager
def institution_context(institution, actor=None):
    token = _institution_id.set(getattr(institution, 'pk', institution))
    actor_token = _actor.set(actor)
    try:
        yield
    finally:
        _actor.reset(actor_token)
        _institution_id.reset(token)


def institution_job(func):
    """Legacy jobs operate on the original institution; institution_command selects another."""
    @wraps(func)
    def wrapped(*args, **kwargs):
        with institution_context(owned_institution_id()):
            return func(*args, **kwargs)
    return wrapped


def validate_institution_links(model, institution_id, values):
    for field in model._meta.concrete_fields:
        if not field.is_relation or field.name == 'institution':
            continue
        related_model = field.remote_field.model
        if not any(f.name == 'institution' for f in related_model._meta.fields):
            continue
        value = values.get(field.attname, values.get(field.name))
        if value is None:
            continue
        value = getattr(value, 'pk', value)
        if not related_model._base_manager.filter(pk=value, institution_id=institution_id).exists():
            raise ValidationError({field.name: 'Choose a record belonging to this institution.'})


class InstitutionQuerySet(models.QuerySet):
    def _clone(self):
        clone = super()._clone()
        clone._scoped_institution_id = getattr(self, '_scoped_institution_id', None)
        return clone

    def _apply_institution(self):
        institution_id = current_institution_id()
        actor = _actor.get()
        marker = (institution_id, actor.pk if actor else None)
        if institution_id and getattr(self, '_scoped_institution_id', None) != marker:
            self._result_cache = None
            self.query.add_q(models.Q(institution_id=institution_id))
            self._scoped_institution_id = marker
            actor = _actor.get()
            path = COURSE_PATHS.get(self.model._meta.label_lower)
            if actor and path is not None and not (actor.is_superuser or actor.role == 'admin'):
                self.query.add_q(models.Q(**{(path + '__' if path else '') + 'pk__in': allowed_course_ids(actor)}))
        return self

    def _chain(self):
        # Class-level view querysets and copied form fields are scoped when cloned.
        return super()._chain()._apply_institution()

    def _fetch_all(self):
        self._apply_institution()
        return super()._fetch_all()

    def count(self):
        return super(InstitutionQuerySet, self._apply_institution()).count()

    def exists(self):
        return super(InstitutionQuerySet, self._apply_institution()).exists()

    def iterator(self, *args, **kwargs):
        self._apply_institution()
        return super().iterator(*args, **kwargs)

    def aggregate(self, *args, **kwargs):
        self._apply_institution()
        return super().aggregate(*args, **kwargs)

    def update(self, **kwargs):
        self._apply_institution()
        if 'institution' in kwargs or 'institution_id' in kwargs:
            raise ValidationError('Institution ownership cannot be changed by a bulk update.')
        if current_institution_id():
            validate_institution_links(self.model, current_institution_id(), kwargs)
        return super().update(**kwargs)

    def delete(self):
        self._apply_institution()
        return super().delete()

    def bulk_create(self, objs, **kwargs):
        objs = list(objs)
        for obj in objs:
            obj.validate_institution()
        return super().bulk_create(objs, **kwargs)

    def bulk_update(self, objs, fields, **kwargs):
        objs = list(objs)
        if 'institution' in fields or 'institution_id' in fields:
            raise ValidationError('Institution ownership cannot be changed by a bulk update.')
        for obj in objs:
            obj.validate_institution()
        return super().bulk_update(objs, fields, **kwargs)


class InstitutionManager(models.Manager.from_queryset(InstitutionQuerySet)):
    def get_queryset(self):
        return super().get_queryset()._apply_institution()


def validate_institution_m2m(sender, instance, action, model, pk_set, **kwargs):
    if action != 'pre_add' or not pk_set:
        return
    institution_id = getattr(instance, 'institution_id', None)
    if institution_id and any(f.name == 'institution' for f in model._meta.fields):
        if model._base_manager.filter(pk__in=pk_set).exclude(institution_id=institution_id).exists():
            raise ValidationError('Related records must belong to the same institution.')


def require_institution_admin(user):
    if not user.is_authenticated or user.role != 'admin':
        raise PermissionDenied('Institution administrator access is required.')


COURSE_PATHS = {
 'chatbot.chatsession': 'course', 'chatbot.chatmessage': 'session__course',
 'learning.course': '', 'learning.topic': 'course', 'learning.material': 'course',
 'learning.baselineassessment': 'course', 'learning.assessmentquestion': 'assessment__course',
 'learning.assessmentattempt': 'assessment__course', 'learning.attemptanswer': 'attempt__assessment__course',
 'learning.quiz': 'course', 'learning.quizquestion': 'quiz__course', 'learning.quizattempt': 'quiz__course',
 'learning.quizanswer': 'attempt__quiz__course', 'learning.lecturerprompt': 'course',
 'ingestion.contentchunk': 'material__course', 'ingestion.ingestedresource': 'material__course',
 'ingestion.researchrun': 'course', 'ingestion.researchtheme': 'run__course',
 'ingestion.researchvideo': 'run__course', 'ingestion.researchvideotheme': 'video__run__course',
 'recommendations.recommendation': 'material__course', 'recommendations.materialembeddingcluster': 'material__course',
 'analytics_app.questiontheme': 'course', 'analytics_app.analyzedquestion': 'course',
}

def allowed_course_ids(user):
    from learning.models import Course
    courses = Course._base_manager.filter(institution_id=user.institution_id)
    if not (user.is_superuser or user.role == 'admin'):
        relation = {'lecturer': 'lecturers', 'ta': 'teaching_assistants'}.get(user.role, 'students')
        courses = courses.filter(**{relation: user})
    return courses.values_list('pk', flat=True)

def scope_key():
    actor = _actor.get()
    return f"{current_institution_id() or 'maintenance'}:{actor.pk if actor else 'system'}"

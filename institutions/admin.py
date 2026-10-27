from django.contrib import admin
from .models import Institution, Department

@admin.register(Institution)
class InstitutionAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'is_active']
    readonly_fields = ['slug', 'is_original', 'join_code']
    def has_module_permission(self, request):
        return request.user.is_superuser and request.user.institution.is_original
    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)
    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)
    def has_add_permission(self, request):
        return False
    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'code']

from pathlib import PurePosixPath

def material_upload_path(instance, filename):
    filename = PurePosixPath(filename.replace('\\', '/')).name
    return f'institutions/{instance.institution_id}/modules/{instance.course_id}/materials/{filename}'

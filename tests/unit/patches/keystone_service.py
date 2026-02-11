from unittest.mock import patch

patch_keystone_get_project_entry = patch(
    "metadata_backend.services.keystone_service.KeystoneServiceHandler.get_project_entry",
    return_value={},
)
patch_keystone_get_ec2 = patch(
    "metadata_backend.services.keystone_service.KeystoneServiceHandler.get_ec2_for_project",
    return_value={},
)
patch_keystone_delete_ec2 = patch(
    "metadata_backend.services.keystone_service.KeystoneServiceHandler.delete_ec2_from_project",
    return_value=204,
)

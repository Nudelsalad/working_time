# Copyright (c) 2025
# Re-run custom field creation to add OpenProject sync fields introduced later.

def execute():
    from working_time.install import make_custom_fields
    make_custom_fields()

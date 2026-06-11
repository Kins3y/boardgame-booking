def validate_map(systems, connections):
    errors = []
    warnings = []

    if len(systems) < 2:
        errors.append("Map must contain at least 2 systems")

    start_systems = [system for system in systems if system.is_start]

    if len(start_systems) < 2:
        errors.append("Map must contain at least 2 start systems")

    archive_systems = [system for system in systems if system.is_archive]

    if len(archive_systems) == 0:
        warnings.append("Map has no archive systems")

    connected_system_ids = set()

    for connection in connections:
        connected_system_ids.add(connection.from_system_id)
        connected_system_ids.add(connection.to_system_id)

    isolated_systems = [
        system.id for system in systems
        if system.id not in connected_system_ids
    ]

    if isolated_systems:
        warnings.append(f"Isolated systems found: {isolated_systems}")

    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings
    }
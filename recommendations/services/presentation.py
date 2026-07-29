def unique_recommendations(recommendations):
    seen_material_ids = set()
    unique_items = []
    for recommendation in recommendations:
        material_id = recommendation.material_id
        if material_id in seen_material_ids:
            continue
        seen_material_ids.add(material_id)
        unique_items.append(recommendation)
    return unique_items

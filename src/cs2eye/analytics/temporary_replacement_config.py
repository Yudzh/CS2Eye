STAND_IN_PENALTIES = {1: -3.0, 2: -6.0, 3: -9.0}


def stand_in_penalty(replacements_count: int) -> float:
    if replacements_count <= 0:
        return 0.0
    return STAND_IN_PENALTIES[min(replacements_count, 3)]

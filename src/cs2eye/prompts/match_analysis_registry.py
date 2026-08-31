from cs2eye.prompts import match_analysis_v3, match_analysis_v4, match_analysis_v5


PROMPT_BUILDERS = {
    match_analysis_v3.PROMPT_VERSION: (
        match_analysis_v3.build_system_prompt, match_analysis_v3.build_user_input,
    ),
    match_analysis_v4.PROMPT_VERSION: (
        match_analysis_v4.build_system_prompt, match_analysis_v4.build_user_input,
    ),
    match_analysis_v5.PROMPT_VERSION: (
        match_analysis_v5.build_system_prompt, match_analysis_v5.build_user_input,
    ),
}


def get_plan_prompt(version: str):
    try:
        return PROMPT_BUILDERS[version]
    except KeyError as error:
        raise ValueError(f"Unsupported match explanation prompt: {version}") from error

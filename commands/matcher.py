
import difflib


def match_command(spoken_text, apps_config):
    all_phrases = []
    phrase_to_app = {}

    for app_name, app_data in apps_config.items():
        for phrase in app_data.get("phrases", []):
            normalized_phrase = phrase.lower().strip()
            all_phrases.append(normalized_phrase)
            phrase_to_app[normalized_phrase] = (app_name, app_data.get("path", ""))

    if not all_phrases:
        return None

    spoken_lower = spoken_text.lower().strip()
    matches = difflib.get_close_matches(spoken_lower, all_phrases, n=1, cutoff=0.65)

    if matches:
        best_phrase = matches[0]
        similarity = difflib.SequenceMatcher(None, spoken_lower, best_phrase).ratio() * 100
        app_name, app_path = phrase_to_app[best_phrase]
        return app_name, app_path, similarity
    return None
import typing
import json
import os
import telegram as tg


def get_language_code(obj) -> str:
    """Extracts language code from an object of types: str, tg.Update, tg.Message, tg.User"""
    if type(obj) is str:
        return obj
    elif type(obj) is tg.Update:
        return obj.message.from_user.language_code
    elif type(obj) is tg.Message:
        return obj.from_user.language_code
    elif type(obj) is tg.User:
        return obj.language_code
    else:
        raise TypeError


class BotTranslation:
    def __init__(self, translations_dir, default_language = "en"):
        self.translations_path = translations_dir
        self.languages = []
        self.default_language = default_language
        files = os.listdir(translations_dir)
        # Parse all language files in format: XX.json
        i = 0
        while True:
            if not files[i].endswith(".json"):
                del files[i]
            else:
                self.languages.append(files[i][:-5])
                i += 1
            if i == len(files):
                break
        if default_language not in self.languages:
            raise ValueError

    def get_string(self, lang, name):
        """Get string from name by language"""
        lang = get_language_code(lang)
        if lang not in self.languages:
            lang = self.default_language
        fp = open(f"{self.translations_path}/{lang}.json")
        translation = json.load(fp)
        fp.close()
        if name not in translation:
            if lang != self.default_language:
                return self.get_string(self.default_language, name)
            else:
                raise KeyError
        else:
            return translation[name]

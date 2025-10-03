def preprocess_text(text):
    return text.strip().replace('\r', '[|]').replace('\n', '[||]')

def postprocess_text(text, for_json=True):
    text = text.strip().replace('[|]', '\r').replace('[||]', '\n')
    if for_json:
        # Keep real \r and \n characters
        return text.replace('\\r', '\r').replace('\\n', '\n')
    else:
        # Store as literal \\r and \\n for txt
        return text.replace('\r', '\\r').replace('\n', '\\n')

special_chars = [
    "？？？",
    "{{title}}",
    "???",
    "[{{0}}]",
    "[|]",
    "[||]",
    "……。",
]

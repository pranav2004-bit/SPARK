import unicodedata

from django.conf import settings

from .errors import ContentError


def _field(errors, name, message):
    errors.setdefault(name, []).append(message)


def validate_node_name(name):
    errors = {}
    cleaned = (name or "").strip()
    if not cleaned:
        _field(errors, "name", "Name is required.")
    elif len(cleaned) > settings.CONTENT_NODE_NAME_MAX:
        _field(errors, "name", f"Name must be at most {settings.CONTENT_NODE_NAME_MAX} characters.")
    elif any(unicodedata.category(ch) == "Cc" for ch in cleaned):
        # Control characters (line breaks, tabs, NUL) are refused; letters, digits and symbols are allowed.
        _field(errors, "name", "Name cannot contain control characters.")
    return cleaned, errors


def validate_question_fields(*, text, options, explanation, image_key, image_alt_text, full):
    """Draft saves validate only the fields that are present (full=False).
    Publish validates everything (full=True) and reports every failing field."""
    errors = {}
    cleaned_text = (text or "").strip()
    if full and not cleaned_text:
        _field(errors, "question_text", "Question text is required.")
    if len(cleaned_text) > settings.CONTENT_QUESTION_TEXT_MAX:
        _field(errors, "question_text", f"Question text must be at most {settings.CONTENT_QUESTION_TEXT_MAX} characters.")

    cleaned_explanation = (explanation or "").strip()
    if len(cleaned_explanation) > settings.CONTENT_EXPLANATION_MAX:
        _field(errors, "explanation", f"Explanation must be at most {settings.CONTENT_EXPLANATION_MAX} characters.")

    cleaned_alt = (image_alt_text or "").strip()
    if image_key and not cleaned_alt:
        _field(errors, "image_alt_text", "Alt text is required when an image is present.")
    if len(cleaned_alt) > settings.CONTENT_IMAGE_ALT_TEXT_MAX:
        _field(errors, "image_alt_text", f"Alt text must be at most {settings.CONTENT_IMAGE_ALT_TEXT_MAX} characters.")

    if options is not None:
        opts = options
        if len(opts) > settings.CONTENT_OPTION_MAX:
            _field(errors, "options", f"At most {settings.CONTENT_OPTION_MAX} options are allowed.")
        if full and len(opts) < settings.CONTENT_OPTION_MIN:
            _field(errors, "options", f"At least {settings.CONTENT_OPTION_MIN} options are required to publish.")
        texts = []
        correct = 0
        for idx, opt in enumerate(opts):
            t = (opt.get("option_text") or "").strip()
            if full and not t:
                _field(errors, f"options[{idx}].option_text", "Option text is required.")
            if len(t) > settings.CONTENT_OPTION_TEXT_MAX:
                _field(errors, f"options[{idx}].option_text",
                       f"Option text must be at most {settings.CONTENT_OPTION_TEXT_MAX} characters.")
            texts.append(t.casefold())
            if opt.get("is_correct"):
                correct += 1
        if len(set(texts)) != len(texts):
            _field(errors, "options", "Options must be unique.")
        if full and correct != 1:
            _field(errors, "options", "Exactly one option must be marked correct.")

    if errors:
        raise ContentError("Validation failed.", "validation_error", 400, errors)
    return cleaned_text, cleaned_explanation, cleaned_alt

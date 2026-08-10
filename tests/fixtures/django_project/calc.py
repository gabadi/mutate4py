"""A bystander module (issue 05): not in INSTALLED_APPS, never imported by
django.setup(), so it stays on the warm forking path."""


def is_adult(age):
    return age >= 18


def is_senior(age):
    return age >= 65

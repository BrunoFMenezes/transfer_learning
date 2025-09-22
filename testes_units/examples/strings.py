def reverse(s):
    return s[::-1]

def capitalize_first(s):
    if not isinstance(s, str):
        raise TypeError("expected str")
    if not s:
        return s
    return s[0].upper() + s[1:]

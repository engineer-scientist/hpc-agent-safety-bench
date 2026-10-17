"""Encode files into a single-line shell command (the IRI API turns newlines in job arguments into
command separators, and its GraphQL layer un-escapes backslashes once)."""
def enc_content(txt: str) -> str:
    # for printf '%b': escape backslash, newline, single quote
    return txt.replace("\\", "\\\\").replace("\n", "\\n").replace("'", "\\047")

def write_cmd(path: str, txt: str) -> str:
    return f"printf '%b' '{enc_content(txt)}' > {path}"

def for_api(cmd: str) -> str:
    return cmd.replace("\\", "\\\\")

import json
from collections import namedtuple

def parsed_config(filename):
    with open(filename) as f:
        content = f.read()
    return parsed_content(content)

def parsed_content(content):
    return json.loads(content)
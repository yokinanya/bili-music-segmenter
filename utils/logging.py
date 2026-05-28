import os

import yaml


SAVE_YAML_PATH = os.path.join(
    os.path.dirname(
        os.path.abspath(__file__)),
    'save.yaml')


def save_timestamps(mediab: str, key: object, val: object, config: str = SAVE_YAML_PATH) -> None:
    save = load_config(config)
    if mediab not in save:
        save[mediab] = {}
    save[mediab][key] = val
    save_config(config, save)
    return save


def load_config(config: str) -> dict:
    if not os.path.isfile(config):
        return {}
    with open(config, encoding='UTF-8') as f:
        data = yaml.safe_load(f)
    return data or {}


def save_config(config: str, data: dict) -> None:
    with open(config, 'w', encoding='UTF-8') as f:
        yaml.safe_dump(data, f, allow_unicode=True)

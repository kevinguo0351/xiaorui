"""Human-confirmed identity fields, separate from conversational preferences."""
import re

FIELDS = [
    {'key': 'person.name', 'label': '您的称呼', 'section': '本人信息', 'limit': 50},
    {'key': 'person.phone', 'label': '本人电话', 'section': '本人信息', 'limit': 32, 'kind': 'tel'},
    {'key': 'home.address', 'label': '家庭住址', 'section': '家庭住址', 'limit': 300, 'kind': 'textarea',
     'placeholder': '请填写城市、区、小区、楼栋和门牌号'},
    {'key': 'contact.primary.name', 'label': '子女或主要联系人姓名', 'section': '主要联系人', 'limit': 50},
    {'key': 'contact.primary.relationship', 'label': '与您的关系', 'section': '主要联系人', 'limit': 30},
    {'key': 'contact.primary.phone', 'label': '子女或主要联系人电话', 'section': '主要联系人', 'limit': 32, 'kind': 'tel'},
    {'key': 'contact.backup.name', 'label': '备用联系人姓名', 'section': '备用联系人', 'limit': 50},
    {'key': 'contact.backup.relationship', 'label': '与您的关系', 'section': '备用联系人', 'limit': 30},
    {'key': 'contact.backup.phone', 'label': '备用联系人电话', 'section': '备用联系人', 'limit': 32, 'kind': 'tel'},
]
BY_KEY = {f['key']: f for f in FIELDS}


class ProfileConflict(ValueError):
    pass


def is_critical(key):
    # Reserve common aliases too: a model cannot bypass the card via home_address.
    return key in BY_KEY or bool(re.search(
        r'(^|[_.-])(home|address|phone|telephone|mobile|contact|child|daughter|son|emergency)([_.-]|$)', key or ''))


def validate_fields(fields):
    if not isinstance(fields, dict) or not fields or set(fields) - BY_KEY.keys():
        raise ValueError('请只修改资料卡中已有的字段。')
    result = {}
    for key, value in fields.items():
        field = BY_KEY[key]
        if not isinstance(value, str) or len(value) > field['limit']:
            raise ValueError(f'{field["label"]}最多填写{field["limit"]}字。')
        value = value.strip()
        if field.get('kind') == 'tel' and value:
            normalized = re.sub(r'[\s()（）-]', '', value)
            if not re.fullmatch(r'\+?[0-9]{5,20}', normalized):
                raise ValueError(f'请核对{field["label"]}，填写完整号码，可包含国家区号。')
            value = normalized
        result[key] = value
    return result
